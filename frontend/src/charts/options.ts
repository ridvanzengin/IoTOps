import type { EChartsOption } from "echarts-for-react";
import type { Chart, SeriesConfig } from "../types/dashboard";
import type { Event } from "../types/event";

type Row = Record<string, unknown>;

// Colorblind-safe categorical palette (Okabe-Ito derived). Two variants,
// not one -- the dark-tuned hues (light, saturated) that read well against
// this app's dark background would wash out on a light one, so light mode
// gets the same hues darkened for contrast instead of reusing them as-is.
// Read live (not a module-level constant) so a chart rebuilt after a theme
// toggle -- see ChartPreview.tsx's useMemo, which depends on useTheme()'s
// theme value precisely so this recomputes -- picks up the current theme.
const CHART_COLORS_DARK = ["#a78bfa", "#4dd4ac", "#f0a83c", "#5eb1ef", "#f2607d", "#c9a227"];
const CHART_COLORS_LIGHT = ["#7c3aed", "#0d9488", "#b45309", "#0369a1", "#be123c", "#854d0e"];

function isLightTheme(): boolean {
  return document.documentElement.dataset.theme === "light";
}

export function getChartColors(): string[] {
  return isLightTheme() ? CHART_COLORS_LIGHT : CHART_COLORS_DARK;
}

// Matches --text's current theme value (index.css) so axis labels and
// gridlines read as one subtle, muted system instead of gridlines standing
// out more than the labels next to them. Gridlines reuse this at low
// opacity.
function getAxisLabelColor(): string {
  return isLightTheme() ? "#57606a" : "#9ca3af";
}

function getGridlineStyle(): { color: string; opacity: number } {
  return { color: getAxisLabelColor(), opacity: 0.2 };
}

function axisValues(rows: Row[], field: string): unknown[] {
  return rows.map((row) => row[field]);
}

function formatAxisValue(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return String(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// Category axes render one explicit tick per row -- a dense time-series
// query (e.g. a 1h range at a 20s publish interval is ~180 rows) is far
// more labels than can fit without overlapping. Thin to a fixed target
// count instead of relying on ECharts's default "auto" interval, which
// wasn't skipping enough to stay readable. No-ops for short category
// lists (e.g. a bar chart's handful of machine/array ids).
const TARGET_VISIBLE_AXIS_LABELS = 8;

function categoryAxisLabelInterval(pointCount: number): number {
  if (pointCount <= TARGET_VISIBLE_AXIS_LABELS) return 0;
  return Math.ceil(pointCount / TARGET_VISIBLE_AXIS_LABELS) - 1;
}

// connectNulls: false (set below) only creates a visible break where the
// data array actually has an explicit null -- it does nothing for a gap
// where a point in time simply has no row at all, which is exactly what
// a real outage (e.g. an Automater stopped and redeployed) looks like
// from a plain "SELECT time, value FROM ..." query with no gap-filling.
// The precise fix belongs in the query itself (TimescaleDB's
// time_bucket_gapfill(), leaving genuine gaps NULL rather than
// interpolating with locf()) -- not something this chart layer can do
// for an arbitrary hand-written panel query. This is the client-side
// fallback: a *relative* threshold (multiples of this series' own
// median sampling interval, not a fixed duration -- a rule evaluated
// every 10s and one every 5m are both "normal," just at different
// paces), inserting a synthetic null at the midpoint of any gap far
// wider than that, so connectNulls: false actually has something to
// break on.
function insertGapBreaks(points: [unknown, unknown][]): [unknown, unknown][] {
  if (points.length < 3) return points;
  const times = points.map(([t]) => new Date(t as string).getTime());
  const deltas: number[] = [];
  for (let i = 1; i < times.length; i++) {
    const delta = times[i] - times[i - 1];
    if (delta > 0) deltas.push(delta);
  }
  if (deltas.length === 0) return points;
  const sortedDeltas = [...deltas].sort((a, b) => a - b);
  const medianDelta = sortedDeltas[Math.floor(sortedDeltas.length / 2)];
  if (medianDelta <= 0) return points;
  const gapThreshold = medianDelta * 4;

  const result: [unknown, unknown][] = [points[0]];
  for (let i = 1; i < points.length; i++) {
    const prevTime = times[i - 1];
    const curTime = times[i];
    if (curTime - prevTime > gapThreshold) {
      result.push([new Date(prevTime + (curTime - prevTime) / 2).toISOString(), null]);
    }
    result.push(points[i]);
  }
  return result;
}

// Splits long/tidy rows (one row per series-name/value pair) into one
// ECharts series per distinct value of `seriesByField`. Each series gets its
// own independent list of [x, value] points rather than being aligned to a
// shared category axis — series from independent sources (e.g. one row per
// device per reading) essentially never share an exact x value, so aligning
// them to one shared axis would leave every series as isolated null-padded
// points with nothing to connect. A time-value axis lets each series draw
// its own line through its own points regardless of what the others report.
function buildLongFormatSeries(
  rows: Row[],
  xField: string,
  valueField: string,
  seriesByField: string,
  defaultType: "line" | "bar" | "scatter",
): EChartsOption["series"] {
  const seriesData = new Map<string, [unknown, unknown][]>();
  for (const row of rows) {
    const name = String(row[seriesByField]);
    if (!seriesData.has(name)) {
      seriesData.set(name, []);
    }
    seriesData.get(name)!.push([row[xField], row[valueField]]);
  }

  return Array.from(seriesData.entries()).map(([name, data]) => {
    const sorted = [...data].sort((a, b) => new Date(a[0] as string).getTime() - new Date(b[0] as string).getTime());
    return {
      type: defaultType,
      name,
      data: defaultType === "line" ? insertGapBreaks(sorted) : sorted,
      smooth: defaultType === "line" ? true : undefined,
      // No dots on the line itself, and an explicit gap (no connecting
      // segment) wherever a value is null -- lets a real data loss read as
      // a visible break instead of silently interpolating across it.
      showSymbol: defaultType === "line" ? false : undefined,
      connectNulls: defaultType === "line" ? false : undefined,
    };
  });
}

function buildXyOption(
  chart: {
    x_axis: string;
    y_axis: string;
    series: SeriesConfig[];
    series_by?: string | null;
    legend: boolean;
    tooltip: boolean;
  },
  defaultType: "line" | "bar" | "scatter",
  rows: Row[],
): EChartsOption {
  if (chart.series_by) {
    const series = buildLongFormatSeries(rows, chart.x_axis, chart.y_axis, chart.series_by, defaultType);
    return {
      color: getChartColors(),
      tooltip: chart.tooltip ? { trigger: "axis" } : undefined,
      legend: chart.legend ? { top: 0, right: 0, textStyle: { fontSize: 11 } } : undefined,
      grid: { top: chart.legend ? 28 : 12, left: 4, right: 8, bottom: 26, containLabel: true },
      xAxis: {
        type: "time",
        // hideOverlap measures actual rendered label bounding boxes and
        // hides whichever would visually collide -- adapts to the panel's
        // real width/font size instead of guessing a fixed tick count,
        // which a plain "time" axis with no interval control doesn't do
        // on its own (ECharts still tried to place more ticks than a
        // narrow half-width panel could legibly fit).
        axisLabel: { formatter: formatAxisValue, hideOverlap: true, fontSize: 11, color: getAxisLabelColor() },
      },
      yAxis: {
        type: "value",
        axisLabel: { fontSize: 11, color: getAxisLabelColor() },
        splitLine: { lineStyle: getGridlineStyle() },
      },
      series,
    };
  }

  const allSeries: SeriesConfig[] = [
    { field: chart.y_axis, axis: "left", type: defaultType },
    ...chart.series,
  ];
  const usesRightAxis = allSeries.some((series) => series.axis === "right");

  return {
    color: getChartColors(),
    tooltip: chart.tooltip ? { trigger: "axis" } : undefined,
    legend: chart.legend ? { top: 0, right: 0, textStyle: { fontSize: 11 } } : undefined,
    // `right: 8` is a floor, not the actual reserved space -- containLabel
    // grows it to fit the right axis's real label width when one exists,
    // so a bigger fixed number here (previously 36) was just adding blank
    // space on top of what the labels actually need.
    grid: {
      top: chart.legend ? 28 : 12,
      left: 4,
      right: 8,
      bottom: 26,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: axisValues(rows, chart.x_axis),
      // Only format as a time-of-day string when x_axis really is the
      // "time" column (the literal-name convention every time-series
      // panel in this app already uses) -- a plain category column (e.g.
      // a bar chart's "machine_id") must render its raw label as-is.
      // formatAxisValue's Date-parsing fallback is dangerously lenient
      // (`new Date("cnc-01")` silently parses as a real date instead of
      // failing), so applying it unconditionally here previously mangled
      // any category value that happened to look date-ish.
      axisLabel:
        chart.x_axis === "time"
          ? {
              formatter: formatAxisValue,
              interval: categoryAxisLabelInterval(rows.length),
              hideOverlap: true,
              fontSize: 11,
              color: getAxisLabelColor(),
            }
          : {
              formatter: (value: unknown) => String(value),
              interval: categoryAxisLabelInterval(rows.length),
              hideOverlap: true,
              fontSize: 11,
              color: getAxisLabelColor(),
            },
    },
    yAxis: usesRightAxis
      ? [
          {
            type: "value",
            axisLabel: { fontSize: 11, color: getAxisLabelColor() },
            splitLine: { lineStyle: getGridlineStyle() },
          },
          {
            type: "value",
            axisLabel: { fontSize: 11, color: getAxisLabelColor() },
            position: "right",
            splitLine: { show: false },
            // Without this, each value axis independently auto-scales its
            // own min/max/tick count from its own series' data range (e.g.
            // temperature 0-50 vs humidity 0-80) -- the two axes' gridlines
            // land at different heights even though only the left axis's
            // splitLine is drawn, so the right axis's own labels don't line
            // up with what's actually on the chart. Aligns this axis's
            // ticks to the left axis's instead of computing its own.
            alignTicks: true,
          },
        ]
      : {
          type: "value",
          axisLabel: { fontSize: 11, color: getAxisLabelColor() },
          splitLine: { lineStyle: getGridlineStyle() },
        },
    series: allSeries.map((series) => {
      const type = series.type ?? defaultType;
      return {
        type,
        name: series.label ?? series.field,
        yAxisIndex: usesRightAxis && series.axis === "right" ? 1 : 0,
        data: axisValues(rows, series.field),
        smooth: type === "line" ? true : undefined,
        // No dots on the line itself, and an explicit gap (no connecting
        // segment) wherever a value is null -- lets a real data loss read
        // as a visible break instead of silently interpolating across it.
        showSymbol: type === "line" ? false : undefined,
        connectNulls: type === "line" ? false : undefined,
      };
    }),
  };
}

const EVENT_MARK_COLOR: Record<Event["flag"], string> = {
  match: "#f2607d",
  clear: "#4dd4ac",
};

// One shape per Rule (cycled if more than 3 are overlaid on one panel) so
// multiple overlaid rules stay visually distinguishable from each other,
// independent of color -- color alone always means active/resolved,
// never rule identity.
const EVENT_SYMBOLS = ["diamond", "circle", "rect"];

// Category axes position by exact value equality against the axis's own
// `data` array (see buildXyOption's wide-format branch) -- an event's
// matched_at timestamp essentially never matches one exactly, so it has
// to snap to whichever category tick is closest in time instead. Returns
// null if no category looks like a timestamp at all (categories aren't
// time-based), rather than snapping to an arbitrary first entry.
function nearestCategoryValue(categories: unknown[], targetIso: string): unknown | null {
  const target = new Date(targetIso).getTime();
  let nearest: unknown = null;
  let nearestDiff = Infinity;
  for (const candidate of categories) {
    const candidateTime = new Date(String(candidate)).getTime();
    if (Number.isNaN(candidateTime)) continue;
    const diff = Math.abs(candidateTime - target);
    if (diff < nearestDiff) {
      nearest = candidate;
      nearestDiff = diff;
    }
  }
  return nearest;
}

interface EventMarker {
  name: string;
  xValue: number | unknown;
  shape: string;
  color: string;
}

const EVENT_MARKER_RADIUS = 7;

// Draws one event marker as a plain zrender shape at an already-resolved
// pixel position -- kept separate from renderItem so the shape math reads
// independently of the coordinate lookup around it.
function eventMarkerShape(shape: string, cx: number, cy: number, color: string) {
  const r = EVENT_MARKER_RADIUS;
  const common = { style: { fill: color } };
  switch (shape) {
    case "circle":
      return { type: "circle", shape: { cx, cy, r }, ...common };
    case "rect": {
      const size = r * 1.6;
      return { type: "rect", shape: { x: cx - size / 2, y: cy - size / 2, width: size, height: size }, ...common };
    }
    case "diamond":
    default:
      return {
        type: "polygon",
        shape: {
          points: [
            [cx, cy - r],
            [cx + r, cy],
            [cx, cy + r],
            [cx - r, cy],
          ],
        },
        ...common,
      };
  }
}

export interface EventOverlay {
  series: NonNullable<EChartsOption["series"]>;
}

// Match/clear events as marker shapes on a fixed top-of-chart lane. Drawn
// as a `custom` series that positions each marker from the grid's own
// pixel rect (`params.coordSys`) plus the x-axis's pixel mapping for that
// event's timestamp -- deliberately not a real data point on any yAxis,
// so a marker's vertical position never depends on (or can collide with)
// the real data's scale. This also means the overlay never needs a
// dedicated yAxis of its own: an earlier version added one (hidden,
// fixed to [0, 1]) for the same fixed-lane effect, but ECharts stacks
// *any* extra yAxis alongside the real left/right axes and reserves real
// margin for it even with show:false -- confirmed empirically -- which
// widened (and for a hidden axis pinned to the left, shifted) the
// chart's side margins just from toggling the overlay on. Going through
// pixels instead of an axis value sidesteps that entirely: toggling the
// overlay can now never move the real axes.
//
// Pie/gauge charts have no natural x-position, so they never get an
// overlay -- gated here, matching what buildChartOption itself supports
// for line/bar/scatter.
export function buildEventOverlay(chart: Chart, rows: Row[], events: Event[]): EventOverlay | null {
  if (events.length === 0) return null;
  if (chart.type !== "line" && chart.type !== "bar" && chart.type !== "scatter") return null;

  const isTimeAxis = Boolean(chart.series_by);
  const categories = isTimeAxis ? null : axisValues(rows, chart.x_axis);

  const ruleShapeIndex = new Map<string, number>();
  for (const event of events) {
    if (!ruleShapeIndex.has(event.rule_id)) ruleShapeIndex.set(event.rule_id, ruleShapeIndex.size);
  }

  const markers: EventMarker[] = events
    .map((event) => {
      const xValue = isTimeAxis ? new Date(event.matched_at).getTime() : nearestCategoryValue(categories!, event.matched_at);
      if (xValue === null || xValue === undefined || Number.isNaN(xValue)) return null;
      return {
        name: `${event.flag === "match" ? "Active" : "Resolved"}: ${event.rule_name}`,
        xValue,
        shape: EVENT_SYMBOLS[(ruleShapeIndex.get(event.rule_id) ?? 0) % EVENT_SYMBOLS.length],
        color: EVENT_MARK_COLOR[event.flag],
      };
    })
    .filter((entry): entry is EventMarker => entry !== null);

  if (markers.length === 0) return null;

  return {
    series: [
      {
        type: "custom",
        name: "Events",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: markers,
        renderItem: (params, api) => {
          const marker = markers[params.dataIndex];
          const [pixelX] = api.coord([marker.xValue, 0]);
          const coordSys = params.coordSys as { x: number; y: number; width: number; height: number };
          // Above coordSys.y (the grid's top edge / the data's own top
          // gridline), not below it -- markers belong in the top margin,
          // clear of the highest data point, regardless of how close the
          // real data happens to sit to the axis's current max.
          const pixelY = coordSys.y - EVENT_MARKER_RADIUS - 3;
          if (pixelX < coordSys.x || pixelX > coordSys.x + coordSys.width) return undefined;
          return eventMarkerShape(marker.shape, pixelX, pixelY, marker.color);
        },
        tooltip: { trigger: "item", formatter: (params) => markers[(params as { dataIndex: number }).dataIndex]?.name ?? "" },
      },
    ],
  };
}

export function buildChartOption(chart: Chart, rows: Row[]): EChartsOption {
  switch (chart.type) {
    case "line":
      return buildXyOption(chart, "line", rows);
    case "bar":
      return buildXyOption(chart, "bar", rows);
    case "scatter":
      return buildXyOption(chart, "scatter", rows);
    case "pie":
      return {
        color: getChartColors(),
        tooltip: chart.tooltip ? { trigger: "item" } : undefined,
        legend: chart.legend ? { top: 0, right: 0, textStyle: { fontSize: 11 } } : undefined,
        series: [
          {
            type: "pie",
            radius: "70%",
            data: rows.map((row) => ({
              name: String(row[chart.label_field]),
              value: row[chart.value_field],
            })),
          },
        ],
      };
    case "gauge": {
      const value = rows.length > 0 ? Number(rows[0][chart.value_field]) : 0;
      return {
        series: [
          {
            type: "gauge",
            min: chart.min,
            max: chart.max,
            radius: "90%",
            progress: { show: true, width: 10 },
            axisLine: { lineStyle: { width: 10 } },
            pointer: { show: false },
            itemStyle: { color: getChartColors()[0] },
            data: [{ value }],
          },
        ],
      };
    }
    default: {
      const exhaustiveCheck: never = chart;
      throw new Error(`Unsupported chart type: ${JSON.stringify(exhaustiveCheck)}`);
    }
  }
}
