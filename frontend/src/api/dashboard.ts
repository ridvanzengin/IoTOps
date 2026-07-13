import { apiRequest } from "./client";
import type {
  Dashboard,
  DashboardInputPayload,
  DashboardLayoutInputPayload,
  DashboardQueryPreview,
  PanelInputPayload,
  PanelQueryOverrides,
  PanelQueryResult,
  VariableOptionsRequest,
  VariableOptionsResult,
} from "../types/dashboard";
import type { TelemetrySqlQueryResult } from "../types/telemetry";

export function listDashboards(): Promise<Dashboard[]> {
  return apiRequest<Dashboard[]>("/api/dashboard");
}

export function getDashboard(id: string): Promise<Dashboard> {
  return apiRequest<Dashboard>(`/api/dashboard/${id}`);
}

export function createDashboard(payload: DashboardInputPayload): Promise<Dashboard> {
  return apiRequest<Dashboard>("/api/dashboard", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateDashboard(id: string, payload: DashboardInputPayload): Promise<Dashboard> {
  return apiRequest<Dashboard>(`/api/dashboard/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteDashboard(id: string): Promise<void> {
  return apiRequest<void>(`/api/dashboard/${id}`, { method: "DELETE" });
}

export function addPanel(dashboardId: string, payload: PanelInputPayload): Promise<Dashboard> {
  return apiRequest<Dashboard>(`/api/dashboard/${dashboardId}/panel`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updatePanel(
  dashboardId: string,
  panelId: string,
  payload: PanelInputPayload,
): Promise<Dashboard> {
  return apiRequest<Dashboard>(`/api/dashboard/${dashboardId}/panel/${panelId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function removePanel(dashboardId: string, panelId: string): Promise<Dashboard> {
  return apiRequest<Dashboard>(`/api/dashboard/${dashboardId}/panel/${panelId}`, {
    method: "DELETE",
  });
}

export function saveLayout(
  dashboardId: string,
  payload: DashboardLayoutInputPayload,
): Promise<Dashboard> {
  return apiRequest<Dashboard>(`/api/dashboard/${dashboardId}/layout`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function runPanelQuery(
  dashboardId: string,
  panelId: string,
  overrides: PanelQueryOverrides,
): Promise<PanelQueryResult> {
  return apiRequest<PanelQueryResult>(`/api/dashboard/${dashboardId}/panel/${panelId}/query`, {
    method: "POST",
    body: JSON.stringify(overrides),
  });
}

export function previewDashboardQuery(
  dashboardId: string,
  payload: DashboardQueryPreview,
): Promise<TelemetrySqlQueryResult> {
  return apiRequest<TelemetrySqlQueryResult>(`/api/dashboard/${dashboardId}/preview-query`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resolveVariableOptions(
  dashboardId: string,
  payload: VariableOptionsRequest,
): Promise<VariableOptionsResult> {
  return apiRequest<VariableOptionsResult>(`/api/dashboard/${dashboardId}/variables/options`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
