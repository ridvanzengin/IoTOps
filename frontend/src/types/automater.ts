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

export interface ConditionPayload {
  column: string;
  operator: ConditionOperator;
  value: number | string | boolean;
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
  table: string;
  operator: RuleOperator;
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
