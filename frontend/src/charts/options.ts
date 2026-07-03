import type { EChartsOption } from "echarts-for-react";
import type { Chart } from "../types/dashboard";

type Row = Record<string, unknown>;

// Colorblind-safe categorical palette (Okabe-Ito derived), tuned for the
// app's dark UI so series stay distinguishable against a dark background.
const CHART_COLORS = ["#a78bfa", "#4dd4ac", "#f0a83c", "#5eb1ef", "#f2607d", "#c9a227"];

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
  chart: { x_axis: string; y_axis: string; legend: boolean; tooltip: boolean },
  seriesType: "line" | "bar" | "scatter",
  rows: Row[],
  extra: Record<string, unknown> = {},
): EChartsOption {
  return {
    color: CHART_COLORS,
    tooltip: chart.tooltip ? { trigger: "axis" } : undefined,
    legend: chart.legend ? { top: 0, right: 0, textStyle: { fontSize: 11 } } : undefined,
    grid: { top: chart.legend ? 28 : 12, left: 4, right: 8, bottom: 26, containLabel: true },
    xAxis: {
      type: "category",
      data: axisValues(rows, chart.x_axis),
      axisLabel: { formatter: formatAxisValue, fontSize: 11 },
    },
    yAxis: { type: "value", axisLabel: { fontSize: 11 } },
    series: [
      {
        type: seriesType,
        data: axisValues(rows, chart.y_axis),
        ...extra,
      },
    ],
  };
}

export function buildChartOption(chart: Chart, rows: Row[]): EChartsOption {
  switch (chart.type) {
    case "line":
      return buildXyOption(chart, "line", rows, { smooth: true });
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
