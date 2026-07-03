export interface LineChart {
  type: "line";
  title: string;
  x_axis: string;
  y_axis: string;
  series: string[];
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
  series: string[];
  legend: boolean;
  tooltip: boolean;
  theme: string;
}

export interface ScatterChart {
  type: "scatter";
  title: string;
  x_axis: string;
  y_axis: string;
  series: string[];
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
  default: string | null;
  type: string;
  options: string[];
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
