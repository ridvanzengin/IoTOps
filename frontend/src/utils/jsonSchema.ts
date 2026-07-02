import type { JsonSchema } from "../types/plugin";

export function defaultsFromSchema(schema: JsonSchema): Record<string, unknown> {
  const properties = schema.properties ?? {};
  const defaults: Record<string, unknown> = {};
  for (const [key, propertySchema] of Object.entries(properties)) {
    if (propertySchema.default !== undefined) {
      defaults[key] = propertySchema.default;
    }
  }
  return defaults;
}
