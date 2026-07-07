import { useEffect, useRef } from "react";
import ReactECharts from "echarts-for-react";
import { buildChartOption } from "../charts/options";
import type { Chart } from "../types/dashboard";

interface ChartPreviewProps {
  chart: Chart;
  rows: Record<string, unknown>[];
  height?: number | string;
}

export function ChartPreview({ chart, rows, height = 260 }: ChartPreviewProps) {
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
          option={buildChartOption(chart, rows)}
          style={{ height: "100%", width: "100%" }}
          notMerge
        />
      )}
    </div>
  );
}
