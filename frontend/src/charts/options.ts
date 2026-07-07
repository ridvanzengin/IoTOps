import type { EChartsOption } from "echarts-for-react";
import type { Chart, SeriesConfig } from "../types/dashboard";

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
