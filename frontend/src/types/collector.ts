export type CollectorStatus =
  | "created"
  | "stopped"
  | "starting"
  | "running"
  | "unhealthy"
  | "stopping"
  | "error";

export interface PluginInstance {
  id: string;
  plugin_type: string;
  enabled: boolean;
  configuration: Record<string, unknown>;
}

export interface InputPluginInstance extends PluginInstance {
  name: string;
}

export type ProcessorPluginInstance = PluginInstance;
export type OutputPluginInstance = PluginInstance;

export interface DockerConfig {
  image: string;
  container_name: string;
  network: string;
  restart_policy: string;
  volumes: string[];
  environment: Record<string, string>;
}

export interface Collector {
  schema_version: number;
  id: string;
  project_id: string;
  name: string;
  description: string;
  enabled: boolean;
  status: CollectorStatus;
  inputs: InputPluginInstance[];
  processors: ProcessorPluginInstance[];
  outputs: OutputPluginInstance[];
  docker: DockerConfig | null;
  created_at: string;
  updated_at: string;
}

export interface InputPluginPayload {
  plugin_type: string;
  name: string;
  enabled: boolean;
  configuration: Record<string, unknown>;
}

export interface ProcessorPluginPayload {
  plugin_type: string;
  enabled: boolean;
  configuration: Record<string, unknown>;
}

export type OutputPluginPayload = ProcessorPluginPayload;

export interface CollectorInputPayload {
  project_id: string;
  name: string;
  description: string;
  enabled: boolean;
  inputs: InputPluginPayload[];
  processors: ProcessorPluginPayload[];
  outputs: OutputPluginPayload[];
}
