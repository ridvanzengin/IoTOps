export type PluginCategory = "input" | "processor" | "output";

export interface JsonSchemaProperty {
  type?: string;
  items?: JsonSchemaProperty;
  minimum?: number;
  maximum?: number;
  minItems?: number;
  enum?: (string | number)[];
  default?: unknown;
  title?: string;
  advanced?: boolean;
}

export interface JsonSchema {
  type?: string;
  required?: string[];
  properties?: Record<string, JsonSchemaProperty>;
}

export interface Plugin {
  id: string;
  name: string;
  category: PluginCategory;
  telegraf_name: string;
  version: string;
  description: string;
  configuration_schema: JsonSchema;
  supported_platforms: string[];
}
