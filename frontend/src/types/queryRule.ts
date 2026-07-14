import type { ResolveMode, RuleSeverity } from "./automater";

// Exactly one of interval/cron is set -- enforced server-side
// (QueryRuleSchedule's own validator). `interval` is a duration string
// ("5m", "1h"), same convention as Rule.ttl. `cron` is a standard 5-field
// cron expression.
export interface QueryRuleSchedule {
  interval: string | null;
  cron: string | null;
}

export interface QueryRuleInput {
  project_id: string;
  name: string;
  description: string;
  sql: string;
  // Kept for display/re-edit if this query was AI-generated -- null for
  // hand-written SQL.
  nl_prompt: string | null;
  // Which SELECTed columns key a match -- same "Identifiers" concept and
  // label as a real-time Rule's, just sourced from the query's own result
  // columns instead of a Telegraf input's tag_keys.
  identifiers: string[];
  category: string;
  severity: RuleSeverity;
  event_type: string;
  message: string;
  resolve_mode: ResolveMode;
  schedule: QueryRuleSchedule;
  enabled: boolean;
}

export interface QueryRule extends QueryRuleInput {
  id: string;
  schema_version: number;
  last_evaluated_at: string | null;
  created_at: string;
  updated_at: string;
}
