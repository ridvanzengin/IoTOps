import type { ConditionPayload, ResolveMode, RuleSeverity } from "./automater";
import type { Chart, Query, Variable } from "./dashboard";
import type { QueryRuleSchedule } from "./queryRule";

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

export interface NeedsContext {
  column: string;
  reason: string;
}

// Set for the lifetime of a suggestion-flow conversation, opened via an
// "Analyze my telemetry"/"Suggest an automation"/"Suggest a panel"/"Suggest
// a dashboard" button rather than the plain Co-pilot icon -- see
// EventsContext.tsx's ActivePanel.
export type CopilotIntent = "analyze-telemetry" | "suggest-automation" | "suggest-panel" | "suggest-dashboard";

export interface AutomaterRuleSuggestionState {
  project_id: string;
  rule_name: string;
  category: string;
  event_type: string;
  severity: RuleSeverity;
  message: string;
  resolve_mode: ResolveMode;
  identifiers: string[];
  table: string;
  conditions: ConditionPayload[];
}

export interface QueryRuleSuggestionState {
  project_id: string;
  name: string;
  category: string;
  event_type: string;
  severity: RuleSeverity;
  message: string;
  resolve_mode: ResolveMode;
  identifiers: string[];
  sql: string;
  schedule: QueryRuleSchedule;
}

export interface PanelSuggestionState {
  dashboard_id: string;
  title: string;
  chart: Chart;
  query: Query;
  time_range: string;
}

// Nested inside DashboardSuggestionState -- no dashboard_id, since it
// doesn't exist yet at proposal time (unlike a standalone panel
// suggestion, which always targets a real, already-existing dashboard).
export interface DashboardPanelSuggestion {
  title: string;
  chart: Chart;
  query: Query;
  time_range: string;
}

export interface DashboardSuggestionState {
  project_id: string;
  name: string;
  description: string;
  variables: Variable[];
  panels: DashboardPanelSuggestion[];
}

// Discriminated on `kind` -- for "automater_rule"/"query_rule"/"panel"
// the route to prefill (/automaters/new, /query-rules/new, or
// /dashboards/{dashboard_id}/panels/new) is derived from it client-side
// rather than sent by the backend, so that routing decision isn't
// duplicated in two layers. "dashboard" has no route to prefill at all --
// there's no dashboard to navigate to until the user confirms it, so its
// suggestion card creates it directly instead (see CopilotChat.tsx's
// handleCreateDashboardSuggestion).
export type CopilotSuggestion =
  | { kind: "automater_rule"; label: string; state: AutomaterRuleSuggestionState }
  | { kind: "query_rule"; label: string; state: QueryRuleSuggestionState }
  | { kind: "panel"; label: string; state: PanelSuggestionState }
  | { kind: "dashboard"; label: string; state: DashboardSuggestionState };
