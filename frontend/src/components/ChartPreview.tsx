import { useEffect, useMemo, useRef } from "react";
import ReactECharts from "echarts-for-react";
import { buildChartOption, buildEventOverlay } from "../charts/options";
import type { Chart } from "../types/dashboard";
import type { Event } from "../types/event";

interface ChartPreviewProps {
  chart: Chart;
  rows: Record<string, unknown>[];
  height?: number | string;
  events?: Event[];
}

export function ChartPreview({ chart, rows, height = 260, events = [] }: ChartPreviewProps) {
  const option = useMemo(() => {
    const base = buildChartOption(chart, rows);
    const overlay = buildEventOverlay(chart, rows, events);
    if (!overlay) return base;
    // Append (not replace) whatever axes buildChartOption already built
    // (a single object, or an array of 2 for a right-axis panel) -- the
    // events axis's index is always the new last slot, so existing
    // series' own yAxisIndex references stay correct.
    const existingYAxis = Array.isArray(base.yAxis) ? base.yAxis : base.yAxis ? [base.yAxis] : [];
    const eventsYAxisIndex = existingYAxis.length;
    const baseSeries: NonNullable<typeof base.series> = Array.isArray(base.series)
      ? base.series
      : base.series
        ? [base.series]
        : [];
    // Explicit legend.data limited to the chart's own series -- without
    // this, ECharts' default "show every series" legend behavior also
    // lists the appended Events overlay series as a togglable legend
    // entry, which reads as part of the data rather than an annotation
    // layer on top of it. buildXyOption only ever produces a single
    // legend object (never an array) when chart.legend is enabled.
    const legend =
      base.legend && !Array.isArray(base.legend)
        ? {
            ...base.legend,
            data: baseSeries
              .map((series: { name?: unknown }) => (typeof series.name === "string" ? series.name : undefined))
              .filter((name: string | undefined): name is string => Boolean(name)),
          }
        : base.legend;
    return {
      ...base,
      legend,
      yAxis: [...existingYAxis, overlay.yAxis],
      series: [
        ...baseSeries,
        ...overlay.series.map((series: { name?: unknown }) => ({ ...series, yAxisIndex: eventsYAxisIndex })),
      ],
    };
  }, [chart, rows, events]);

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReactECharts>(null);

  // Explicitly measure the container via ResizeObserver's own contentRect
  // and pass those exact pixel numbers to echarts' resize(), rather than
  // asking echarts to auto-detect its container size. ECharts' own initial
  // sizing (done once internally, before this component's props even
  // exist) can end up wrong when embedded in a grid layout whose column
  // width is still settling, and asking it to "auto" re-measure later
  // proved unreliable in practice — passing real numbers avoids that
  // ambiguity entirely. The wrapping div is always rendered (not only once
  // rows exist) so the observer reliably attaches from the very first
  // render.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect || rect.width === 0 || rect.height === 0) return;
      chartRef.current?.getEchartsInstance()?.resize({ width: rect.width, height: rect.height });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // The container's size is typically already final by the time the chart
  // actually mounts (once `rows` arrives from the network) — nothing
  // resizes again afterwards, so the ResizeObserver above never fires a
  // second time to correct anything. Force one explicit, synchronous
  // measurement right when the chart appears, instead of waiting on an
  // observer event that may never come.
  useEffect(() => {
    if (rows.length === 0 || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    chartRef.current?.getEchartsInstance()?.resize({ width: rect.width, height: rect.height });
  }, [rows]);

  return (
    <div ref={containerRef} style={{ height, width: "100%" }}>
      {rows.length === 0 ? (
        <div
          style={{
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text)",
            fontSize: 13,
          }}
        >
          Run a query to preview the chart.
        </div>
      ) : (
        <ReactECharts
          ref={chartRef}
          option={option}
          style={{ height: "100%", width: "100%" }}
          notMerge
        />
      )}
    </div>
  );
}
