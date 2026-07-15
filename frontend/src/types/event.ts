import type { ResolveMode, RuleSeverity } from "./automater";

export type EventFlag = "match" | "clear";

// "automater": produced by the Go rule processor via the Celery worker.
// "query_rule": produced by a scheduled SQL evaluation that never touches
// Telegraf/Collector/Automater at all -- see types/queryRule.ts.
export type EventSourceType = "automater" | "query_rule";

export interface Event {
  id: string;
  project_id: string;
  source_type: EventSourceType;
  // Unset for a query_rule-sourced event -- neither concept applies to it.
  automater_id: string | null;
  query_rule_id: string | null;
  rule_id: string;
  rule_name: string;
  table: string | null;
  category: string;
  severity: RuleSeverity;
  event_type: string;
  message: string;
  flag: EventFlag;
  identifier_keys: string[];
  resolve_mode: ResolveMode;
  // Only set on a synthetic `clear` Event written by a manual resolve --
  // never present on a match, or on an ordinary auto-clear.
  resolution_notes: string | null;
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
  // The underlying match Event's own id -- an Occurrence has no identity
  // of its own (it's a live pairing over the Event stream). This is what
  // a "Resolve" API call targets.
  id: string;
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
  source_type: EventSourceType;
  automater_id: string | null;
  query_rule_id: string | null;
  project_id: string;
  tags: Record<string, string>;
  fields: Record<string, unknown>;
  resolve_mode: ResolveMode;
  resolution_notes: string | null;
}

export interface ProjectUnresolvedCount {
  project_id: string;
  count: number;
}

// A page of Occurrences plus the total matching the same filters (time
// range, rule/status, search) -- both computed from one pairing pass over
// the same documents server-side, so `total` is guaranteed consistent with
// what paging through `items` will eventually show.
export interface OccurrencePage {
  items: Occurrence[];
  total: number;
}
