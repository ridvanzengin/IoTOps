import type { ConditionPayload, ResolveMode, RuleSeverity } from "./automater";
import type { Chart, Query } from "./dashboard";
import type { QueryRuleSchedule } from "./queryRule";

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

export interface NeedsContext {
  column: string;
  reason: string;
}

// Set for the lifetime of a suggestion-flow conversation, opened via a
// "Suggest an automation"/"Suggest a panel" button rather than the plain
// Co-pilot icon -- see EventsContext.tsx's ActivePanel.
export type CopilotIntent = "suggest-automation" | "suggest-panel";

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

// Discriminated on `kind` -- the route to prefill (/automaters/new,
// /query-rules/new, or /dashboards/{dashboard_id}/panels/new) is derived
// from it client-side rather than sent by the backend, so that routing
// decision isn't duplicated in two layers.
export type CopilotSuggestion =
  | { kind: "automater_rule"; label: string; state: AutomaterRuleSuggestionState }
  | { kind: "query_rule"; label: string; state: QueryRuleSuggestionState }
  | { kind: "panel"; label: string; state: PanelSuggestionState };
