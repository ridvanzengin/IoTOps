import type {
  CollectorStatus,
  DockerConfig,
  InputPluginInstance,
  InputPluginPayload,
  OutputPluginInstance,
  OutputPluginPayload,
} from "./collector";

export type AutomaterStatus = CollectorStatus;

export type RuleOperator = "AND" | "OR";
export type ConditionOperator = ">" | ">=" | "<" | "<=" | "==" | "!=";
export type RuleSeverity = "low" | "medium" | "high" | "critical";
// auto (default): a clear event auto-fires the moment the condition stops
// matching. manual: never auto-clears -- a human resolves it from the
// Events sidebar instead. See iotops-workspace/ROADMAP.md's "Event
// resolution mode" note.
export type ResolveMode = "auto" | "manual";

export interface ConditionPayload {
  column: string;
  operator: ConditionOperator;
  value: number | string | boolean;
  // How this condition combines with the running result of every
  // condition before it, left-to-right (no precedence/parentheses --
  // "a AND b OR c" is always (a AND b) OR c). Ignored for a rule's first
  // condition. See ROADMAP.md's per-condition join note.
  join: RuleOperator;
}

export interface RulePayload {
  name: string;
  description: string;
  category: string;
  event_type: string;
  severity: RuleSeverity;
  message: string;
  enabled: boolean;
  priority: number;
  resolve_mode: ResolveMode;
  table: string;
  conditions: ConditionPayload[];
  identifiers: string[];
  ttl: string;
}

export interface Rule extends RulePayload {
  id: string;
}

export interface Automater {
  schema_version: number;
  id: string;
  project_id: string;
  name: string;
  description: string;
  enabled: boolean;
  status: AutomaterStatus;
  inputs: InputPluginInstance[];
  rules: Rule[];
  outputs: OutputPluginInstance[];
  docker: DockerConfig | null;
  created_at: string;
  updated_at: string;
}

export interface AutomaterInputPayload {
  project_id: string;
  name: string;
  description: string;
  enabled: boolean;
  inputs: InputPluginPayload[];
  rules: RulePayload[];
  outputs: OutputPluginPayload[];
}

export interface CreateRuleRequest {
  project_id: string;
  rule: RulePayload;
  // Either automater_id (attach to an existing Automater) or
  // automater_name + collector_id (create a new one, deriving its input
  // from that Collector's MQTT input) must be set.
  automater_id?: string | null;
  automater_name?: string | null;
  automater_description?: string;
  collector_id?: string | null;
}
