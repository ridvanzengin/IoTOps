import { apiRequest } from "./client";
import type { QueryRule, QueryRuleInput } from "../types/queryRule";
import type { TelemetrySqlQueryResult } from "../types/telemetry";

export function listQueryRules(projectId?: string): Promise<QueryRule[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return apiRequest<QueryRule[]>(`/api/query-rule${query}`);
}

export function getQueryRule(id: string): Promise<QueryRule> {
  return apiRequest<QueryRule>(`/api/query-rule/${id}`);
}

export function createQueryRule(payload: QueryRuleInput): Promise<QueryRule> {
  return apiRequest<QueryRule>("/api/query-rule", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateQueryRule(id: string, payload: QueryRuleInput): Promise<QueryRule> {
  return apiRequest<QueryRule>(`/api/query-rule/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteQueryRule(id: string): Promise<void> {
  return apiRequest<void>(`/api/query-rule/${id}`, { method: "DELETE" });
}

// Runs the SQL as typed, ahead of saving -- same execution path (and
// timeout) the schedule itself uses, so what's previewed is exactly what
// will run.
export function previewQueryRule(sql: string): Promise<TelemetrySqlQueryResult> {
  return apiRequest<TelemetrySqlQueryResult>("/api/query-rule/preview", {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}
