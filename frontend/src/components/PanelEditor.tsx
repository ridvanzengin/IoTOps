import { useState } from "react";
import { TIME_RANGES } from "../constants/timeRanges";
import type { Chart, ChartType, SeriesConfig, Variable } from "../types/dashboard";

const CHART_TYPES: ChartType[] = ["line", "bar", "scatter", "pie", "gauge"];
const XY_CHART_TYPES: ChartType[] = ["line", "bar", "scatter"];

export function defaultChartForType(type: ChartType, title: string): Chart {
  switch (type) {
    case "line":
      return {
        type: "line",
        title,
        x_axis: "",
        y_axis: "",
        series: [],
        series_by: null,
        legend: true,
        tooltip: true,
        zoom: false,
        theme: "default",
      };
    case "bar":
      return {
        type: "bar",
        title,
        x_axis: "",
        y_axis: "",
        series: [],
        series_by: null,
        legend: true,
        tooltip: true,
        theme: "default",
      };
    case "scatter":
      return {
        type: "scatter",
        title,
        x_axis: "",
        y_axis: "",
        series: [],
        series_by: null,
        legend: true,
        tooltip: true,
        theme: "default",
      };
    case "pie":
      return {
        type: "pie",
        title,
        label_field: "",
        value_field: "",
        legend: true,
        tooltip: true,
        theme: "default",
      };
    case "gauge":
      return { type: "gauge", title, value_field: "", min: 0, max: 100, theme: "default" };
  }
}

interface PanelEditorProps {
  title: string;
  onTitleChange: (title: string) => void;
  chart: Chart;
  onChartChange: (chart: Chart) => void;
  columns: string[];
  timeRange: string;
  onTimeRangeChange: (timeRange: string) => void;
  variables: Variable[];
  onSelectVariableFilter: (variable: Variable) => void;
}

export function PanelEditor({
  title,
  onTitleChange,
  chart,
  onChartChange,
  columns,
  timeRange,
  onTimeRangeChange,
  variables,
  onSelectVariableFilter,
}: PanelEditorProps) {
  const [selectedVariableFilter, setSelectedVariableFilter] = useState("");

  function handleTypeChange(type: ChartType) {
    const base = defaultChartForType(type, title);
    // Switching between line/bar/scatter keeps the axis + series config the
    // user already built — only the mark type changes. Switching to/from
    // pie/gauge still resets, since those charts don't have that shape.
    if (
      (chart.type === "line" || chart.type === "bar" || chart.type === "scatter") &&
      (base.type === "line" || base.type === "bar" || base.type === "scatter")
    ) {
      onChartChange({
        ...base,
        x_axis: chart.x_axis,
        y_axis: chart.y_axis,
        series: chart.series,
        series_by: chart.series_by,
      });
      return;
    }
    onChartChange(base);
  }

  function addSeries() {
    if (chart.type !== "line" && chart.type !== "bar" && chart.type !== "scatter") return;
    onChartChange({
      ...chart,
      series_by: null,
      series: [...chart.series, { field: "", axis: "left", label: null, type: null }],
    });
  }

  function updateSeriesBy(value: string) {
    if (chart.type !== "line" && chart.type !== "bar" && chart.type !== "scatter") return;
    onChartChange({ ...chart, series_by: value || null, series: value ? [] : chart.series });
  }

  function removeSeries(index: number) {
    if (chart.type !== "line" && chart.type !== "bar" && chart.type !== "scatter") return;
    onChartChange({ ...chart, series: chart.series.filter((_, i) => i !== index) });
  }

  function updateSeries(index: number, patch: Partial<SeriesConfig>) {
    if (chart.type !== "line" && chart.type !== "bar" && chart.type !== "scatter") return;
    onChartChange({
      ...chart,
      series: chart.series.map((series, i) => (i === index ? { ...series, ...patch } : series)),
    });
  }

  function fieldSelect(label: string, value: string, onSelect: (value: string) => void) {
    return (
      <label className="field">
        <span>{label}</span>
        <select value={value} onChange={(event) => onSelect(event.target.value)}>
          <option value="">Select a column</option>
          {columns.map((column) => (
            <option key={column} value={column}>
              {column}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <div>
      <label className="field">
        <span>Panel Title</span>
        <input
          value={title}
          onChange={(event) => {
            onTitleChange(event.target.value);
            onChartChange({ ...chart, title: event.target.value });
          }}
        />
      </label>
      <label className="field">
        <span>{XY_CHART_TYPES.includes(chart.type) ? "Default Series Type" : "Chart Type"}</span>
        <select value={chart.type} onChange={(event) => handleTypeChange(event.target.value as ChartType)}>
          {CHART_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Default Time Range</span>
        <select value={timeRange} onChange={(event) => onTimeRangeChange(event.target.value)}>
          {TIME_RANGES.map((range) => (
            <option key={range.code} value={range.code}>
              {range.label}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Add Variable Filter</span>
        <select
          value={selectedVariableFilter}
          disabled={variables.length === 0}
          onChange={(event) => {
            setSelectedVariableFilter(event.target.value);
            const variable = variables.find((v) => v.name === event.target.value);
            if (variable) onSelectVariableFilter(variable);
          }}
        >
          <option value="">None</option>
          {variables.map((variable) => (
            <option key={variable.name} value={variable.name}>
              {variable.label}
            </option>
          ))}
        </select>
      </label>

      {(chart.type === "line" || chart.type === "bar" || chart.type === "scatter") && (
        <>
          {fieldSelect("X Axis", chart.x_axis, (value) => onChartChange({ ...chart, x_axis: value }))}
          {fieldSelect("Y Axis", chart.y_axis, (value) => onChartChange({ ...chart, y_axis: value }))}

          <label className="field">
            <span>Split Series By (optional)</span>
            <select value={chart.series_by ?? ""} onChange={(event) => updateSeriesBy(event.target.value)}>
              <option value="">None (wide format)</option>
              {columns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </label>

          {chart.series_by ? (
            <p className="wizard-panel__hint">
              Each distinct value in "{chart.series_by}" becomes its own series on the left axis.
            </p>
          ) : (
          <div className="field" style={{ maxWidth: "none" }}>
            <span>Additional Series</span>
            {chart.series.map((series, index) => (
              <div
                key={index}
                className="plugin-row"
                style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}
              >
                <select value={series.field} onChange={(event) => updateSeries(index, { field: event.target.value })}>
                  <option value="">Select a column</option>
                  {columns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
                <select
                  value={series.axis}
                  onChange={(event) => updateSeries(index, { axis: event.target.value as SeriesConfig["axis"] })}
                >
                  <option value="left">Left axis</option>
                  <option value="right">Right axis</option>
                </select>
                <select
                  value={series.type ?? ""}
                  onChange={(event) =>
                    updateSeries(index, { type: (event.target.value || null) as SeriesConfig["type"] })
                  }
                >
                  <option value="">Inherit type</option>
                  <option value="line">Line</option>
                  <option value="bar">Bar</option>
                  <option value="scatter">Scatter</option>
                </select>
                <input
                  placeholder="Label (optional)"
                  value={series.label ?? ""}
                  onChange={(event) => updateSeries(index, { label: event.target.value || null })}
                  style={{ flex: 1, minWidth: 120 }}
                />
                <button type="button" className="button button--danger" onClick={() => removeSeries(index)}>
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              className="button"
              style={{ marginTop: 8, alignSelf: "flex-start" }}
              onClick={addSeries}
            >
              + Add Series
            </button>
          </div>
          )}
        </>
      )}

      {chart.type === "pie" && (
        <>
          {fieldSelect("Label Field", chart.label_field, (value) =>
            onChartChange({ ...chart, label_field: value }),
          )}
          {fieldSelect("Value Field", chart.value_field, (value) =>
            onChartChange({ ...chart, value_field: value }),
          )}
        </>
      )}

      {chart.type === "gauge" && (
        <>
          {fieldSelect("Value Field", chart.value_field, (value) =>
            onChartChange({ ...chart, value_field: value }),
          )}
          <label className="field">
            <span>Min</span>
            <input
              type="number"
              value={chart.min}
              onChange={(event) => onChartChange({ ...chart, min: Number(event.target.value) })}
            />
          </label>
          <label className="field">
            <span>Max</span>
            <input
              type="number"
              value={chart.max}
              onChange={(event) => onChartChange({ ...chart, max: Number(event.target.value) })}
            />
          </label>
        </>
      )}
    </div>
  );
}
