export interface SeriesConfig {
  field: string;
  label?: string | null;
  axis: "left" | "right";
  type?: "line" | "bar" | "scatter" | null;
}

export interface LineChart {
  type: "line";
  title: string;
  x_axis: string;
  y_axis: string;
  series: SeriesConfig[];
  series_by?: string | null;
  legend: boolean;
  tooltip: boolean;
  zoom: boolean;
  theme: string;
}

export interface BarChart {
  type: "bar";
  title: string;
  x_axis: string;
  y_axis: string;
  series: SeriesConfig[];
  series_by?: string | null;
  legend: boolean;
  tooltip: boolean;
  theme: string;
}

export interface ScatterChart {
  type: "scatter";
  title: string;
  x_axis: string;
  y_axis: string;
  series: SeriesConfig[];
  series_by?: string | null;
  legend: boolean;
  tooltip: boolean;
  theme: string;
}

export interface PieChart {
  type: "pie";
  title: string;
  label_field: string;
  value_field: string;
  legend: boolean;
  tooltip: boolean;
  theme: string;
}

export interface GaugeChart {
  type: "gauge";
  title: string;
  value_field: string;
  min: number;
  max: number;
  theme: string;
}

export type Chart = LineChart | BarChart | ScatterChart | PieChart | GaugeChart;
export type ChartType = Chart["type"];

export interface Query {
  sql: string;
  variables: Record<string, string>;
  limit: number;
  timezone: string;
}

export interface Variable {
  name: string;
  label: string;
  table: string;
  value_column: string;
  predicate_column: string | null;
  predicate_variable: string | null;
}

export interface PanelPosition {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PanelInputPayload {
  title: string;
  chart: Chart;
  query: Query;
  time_range: string;
  refresh_interval: number;
  position: PanelPosition;
  // Which Rules' match/clear Events overlay this panel's chart -- see
  // iotops-workspace/ROADMAP.md's "Events-as-overlay on Panel charts"
  // note.
  event_rule_ids: string[];
}

export interface Panel extends PanelInputPayload {
  id: string;
}

export interface DashboardInputPayload {
  project_id: string;
  name: string;
  description: string;
  variables: Variable[];
  panels: Panel[];
  layout: Record<string, unknown>;
}

export interface Dashboard extends DashboardInputPayload {
  schema_version: number;
  id: string;
  created_at: string;
  updated_at: string;
}

export interface PanelLayoutUpdate {
  id: string;
  position: PanelPosition;
}

export interface DashboardLayoutInputPayload {
  panels: PanelLayoutUpdate[];
  layout: Record<string, unknown>;
}

export interface PanelQueryOverrides {
  time_range?: string;
  variable_values?: Record<string, string>;
}

export interface PanelQueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
  // The exact [time_from, time_to] window the query's __timeFrom/
  // __timeTo resolved to -- reused by the events-overlay fetch so it
  // asks for the same window the panel's own telemetry query used,
  // not a separately (and therefore slightly later) resolved "now".
  time_from: string;
  time_to: string;
}

export interface DashboardQueryPreview {
  sql: string;
  limit?: number;
  time_range?: string;
  variable_values?: Record<string, string>;
}

export interface VariableOptionsRequest {
  table: string;
  value_column: string;
  predicate_column?: string | null;
  predicate_variable?: string | null;
  variable_values?: Record<string, string>;
}

export interface VariableOptionsResult {
  options: string[];
}
