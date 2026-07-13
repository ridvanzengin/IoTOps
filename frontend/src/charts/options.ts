import type { EChartsOption } from "echarts-for-react";
import type { Chart, SeriesConfig } from "../types/dashboard";
import type { Event } from "../types/event";

type Row = Record<string, unknown>;

// Colorblind-safe categorical palette (Okabe-Ito derived), tuned for the
// app's dark UI so series stay distinguishable against a dark background.
export const CHART_COLORS = ["#a78bfa", "#4dd4ac", "#f0a83c", "#5eb1ef", "#f2607d", "#c9a227"];

// Matches --text's dark-mode value (index.css) so axis labels and gridlines
// read as one subtle, muted system instead of gridlines standing out more
// than the labels next to them. Gridlines reuse this at low opacity.
const AXIS_LABEL_COLOR = "#9ca3af";
const GRIDLINE_STYLE = { color: AXIS_LABEL_COLOR, opacity: 0.2 };

function axisValues(rows: Row[], field: string): unknown[] {
  return rows.map((row) => row[field]);
}

function formatAxisValue(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return String(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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

  return Array.from(seriesData.entries()).map(([name, data]) => ({
    type: defaultType,
    name,
    data: [...data].sort((a, b) => new Date(a[0] as string).getTime() - new Date(b[0] as string).getTime()),
    smooth: defaultType === "line" ? true : undefined,
  }));
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
      color: CHART_COLORS,
      tooltip: chart.tooltip ? { trigger: "axis" } : undefined,
      legend: chart.legend ? { top: 0, right: 0, textStyle: { fontSize: 11 } } : undefined,
      grid: { top: chart.legend ? 28 : 12, left: 4, right: 8, bottom: 26, containLabel: true },
      xAxis: {
        type: "time",
        axisLabel: { formatter: formatAxisValue, fontSize: 11, color: AXIS_LABEL_COLOR },
      },
      yAxis: {
        type: "value",
        axisLabel: { fontSize: 11, color: AXIS_LABEL_COLOR },
        splitLine: { lineStyle: GRIDLINE_STYLE },
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
    color: CHART_COLORS,
    tooltip: chart.tooltip ? { trigger: "axis" } : undefined,
    legend: chart.legend ? { top: 0, right: 0, textStyle: { fontSize: 11 } } : undefined,
    grid: {
      top: chart.legend ? 28 : 12,
      left: 4,
      right: usesRightAxis ? 36 : 8,
      bottom: 26,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: axisValues(rows, chart.x_axis),
      axisLabel: { formatter: formatAxisValue, fontSize: 11, color: AXIS_LABEL_COLOR },
    },
    yAxis: usesRightAxis
      ? [
          {
            type: "value",
            axisLabel: { fontSize: 11, color: AXIS_LABEL_COLOR },
            splitLine: { lineStyle: GRIDLINE_STYLE },
          },
          {
            type: "value",
            axisLabel: { fontSize: 11, color: AXIS_LABEL_COLOR },
            position: "right",
            splitLine: { show: false },
          },
        ]
      : {
          type: "value",
          axisLabel: { fontSize: 11, color: AXIS_LABEL_COLOR },
          splitLine: { lineStyle: GRIDLINE_STYLE },
        },
    series: allSeries.map((series) => {
      const type = series.type ?? defaultType;
      return {
        type,
        name: series.label ?? series.field,
        yAxisIndex: usesRightAxis && series.axis === "right" ? 1 : 0,
        data: axisValues(rows, series.field),
        smooth: type === "line" ? true : undefined,
      };
    }),
  };
}

const EVENT_MARK_COLOR: Record<Event["flag"], string> = {
  match: "#f2607d",
  clear: "#4dd4ac",
};

// One shape per Rule (cycled if more than 4 are overlaid on one panel) so
// multiple overlaid rules stay visually distinguishable from each other,
// independent of color -- color alone always means active/resolved,
// never rule identity. Literal shapes requested: triangle, square,
// diamond -- circle added as a 4th so a 4th+ rule doesn't silently reuse
// triangle without at least *some* visual cue (still ambiguous past 4,
// but the tooltip's rule name is the actual disambiguator at that point).
const EVENT_SYMBOLS = ["triangle", "rect", "diamond", "circle"];

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

export interface EventOverlay {
  series: NonNullable<EChartsOption["series"]>;
  // A dedicated, hidden value axis fixed to [0, 1] -- every event dot
  // plots at y=1 (top) regardless of what the panel's own data is doing,
  // so markers form one consistent band above the chart instead of
  // depending on (and potentially colliding with) the real data's own
  // scale. Appended after whatever axes buildChartOption already
  // produced, so it doesn't disturb their existing yAxisIndex values --
  // the caller (ChartPreview) is responsible for actually appending it
  // and pointing this overlay's series at its index.
  yAxis: NonNullable<EChartsOption["yAxis"]> extends (infer T)[] ? T : never;
}

// Match/clear events as scatter dots on a dedicated top-of-chart lane --
// see the EventOverlay yAxis comment for why a fixed lane instead of
// plotting at the real data's value. Pie/gauge charts have no natural
// x-position, so they never get an overlay -- gated here, matching what
// buildChartOption itself supports for line/bar/scatter.
export function buildEventOverlay(chart: Chart, rows: Row[], events: Event[]): EventOverlay | null {
  if (events.length === 0) return null;
  if (chart.type !== "line" && chart.type !== "bar" && chart.type !== "scatter") return null;

  const isTimeAxis = Boolean(chart.series_by);
  const categories = isTimeAxis ? null : axisValues(rows, chart.x_axis);

  const ruleShapeIndex = new Map<string, number>();
  for (const event of events) {
    if (!ruleShapeIndex.has(event.rule_id)) ruleShapeIndex.set(event.rule_id, ruleShapeIndex.size);
  }

  const data = events
    .map((event) => {
      const xValue = isTimeAxis ? new Date(event.matched_at).getTime() : nearestCategoryValue(categories!, event.matched_at);
      if (xValue === null || xValue === undefined || Number.isNaN(xValue)) return null;
      return {
        name: `${event.flag === "match" ? "Active" : "Resolved"}: ${event.rule_name}`,
        value: [xValue, 1],
        symbol: EVENT_SYMBOLS[(ruleShapeIndex.get(event.rule_id) ?? 0) % EVENT_SYMBOLS.length],
        symbolSize: 11,
        itemStyle: { color: EVENT_MARK_COLOR[event.flag] },
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  if (data.length === 0) return null;

  return {
    series: [
      {
        type: "scatter",
        name: "Events",
        data,
        tooltip: { trigger: "item" },
      },
    ],
    yAxis: { type: "value", show: false, min: 0, max: 1 },
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
        color: CHART_COLORS,
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
            itemStyle: { color: CHART_COLORS[0] },
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
