import type { EChartsOption } from "echarts-for-react";
import type { Chart, SeriesConfig } from "../types/dashboard";

type Row = Record<string, unknown>;

// Colorblind-safe categorical palette (Okabe-Ito derived), tuned for the
// app's dark UI so series stay distinguishable against a dark background.
export const CHART_COLORS = ["#a78bfa", "#4dd4ac", "#f0a83c", "#5eb1ef", "#f2607d", "#c9a227"];

function axisValues(rows: Row[], field: string): unknown[] {
  return rows.map((row) => row[field]);
}

function formatAxisValue(value: unknown): string {
  if (typeof value !== "string") return String(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function buildXyOption(
  chart: {
    x_axis: string;
    y_axis: string;
    series: SeriesConfig[];
    legend: boolean;
    tooltip: boolean;
  },
  defaultType: "line" | "bar" | "scatter",
  rows: Row[],
): EChartsOption {
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
      axisLabel: { formatter: formatAxisValue, fontSize: 11 },
    },
    yAxis: usesRightAxis
      ? [
          { type: "value", axisLabel: { fontSize: 11 } },
          { type: "value", axisLabel: { fontSize: 11 }, position: "right" },
        ]
      : { type: "value", axisLabel: { fontSize: 11 } },
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
