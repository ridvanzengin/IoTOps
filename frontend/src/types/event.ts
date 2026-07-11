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
