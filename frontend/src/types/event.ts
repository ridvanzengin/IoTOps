import type { RuleSeverity } from "./automater";

export type EventFlag = "match" | "clear";

export interface Event {
  id: string;
  project_id: string;
  automater_id: string;
  rule_id: string;
  rule_name: string;
  table: string;
  category: string;
  severity: RuleSeverity;
  event_type: string;
  message: string;
  flag: EventFlag;
  identifier_keys: string[];
  tags: Record<string, string>;
  fields: Record<string, unknown>;
  matched_at: string;
  created_at: string;
}

export interface EventRuleCount {
  project_id: string;
  rule_id: string;
  rule_name: string;
  count: number;
}

export type OccurrenceStatus = "active" | "resolved";

// One match/clear pair (or a lone trailing match, if not yet cleared) --
// what the events list actually renders, not the raw Event stream. See
// backend app/event/models.py's Occurrence docstring for the pairing
// semantics (a re-fire after a clear is a new occurrence, never reopens
// the old one).
export interface Occurrence {
  rule_id: string;
  rule_name: string;
  category: string;
  severity: RuleSeverity;
  event_type: string;
  message: string;
  identifiers: Record<string, string>;
  status: OccurrenceStatus;
  matched_at: string;
  resolved_at: string | null;
  automater_id: string;
  project_id: string;
  tags: Record<string, string>;
  fields: Record<string, unknown>;
}

export interface ProjectUnresolvedCount {
  project_id: string;
  count: number;
}
