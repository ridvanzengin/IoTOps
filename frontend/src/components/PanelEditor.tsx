import type { Chart, ChartType } from "../types/dashboard";

const CHART_TYPES: ChartType[] = ["line", "bar", "scatter", "pie", "gauge"];

export function defaultChartForType(type: ChartType, title: string): Chart {
  switch (type) {
    case "line":
      return {
        type: "line",
        title,
        x_axis: "",
        y_axis: "",
        series: [],
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
}

export function PanelEditor({ title, onTitleChange, chart, onChartChange, columns }: PanelEditorProps) {
  function handleTypeChange(type: ChartType) {
    onChartChange({ ...defaultChartForType(type, title), title });
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
        <span>Chart Type</span>
        <select value={chart.type} onChange={(event) => handleTypeChange(event.target.value as ChartType)}>
          {CHART_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>

      {(chart.type === "line" || chart.type === "bar" || chart.type === "scatter") && (
        <>
          {fieldSelect("X Axis", chart.x_axis, (value) => onChartChange({ ...chart, x_axis: value }))}
          {fieldSelect("Y Axis", chart.y_axis, (value) => onChartChange({ ...chart, y_axis: value }))}
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
