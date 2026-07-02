import type { JsonSchema } from "../types/plugin";

interface PluginConfigFormProps {
  schema: JsonSchema;
  configuration: Record<string, unknown>;
  onChange: (configuration: Record<string, unknown>) => void;
}

export function PluginConfigForm({ schema, configuration, onChange }: PluginConfigFormProps) {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);

  function setField(key: string, value: unknown) {
    onChange({ ...configuration, [key]: value });
  }

  return (
    <div className="plugin-config-form">
      {Object.entries(properties).map(([key, propertySchema]) => {
        const value = configuration[key];
        const label = required.has(key) ? `${key} *` : key;

        if (propertySchema.type === "array") {
          const arrayValue = Array.isArray(value) ? value.join(", ") : "";
          return (
            <label key={key} className="plugin-config-form__field">
              <span>{label}</span>
              <input
                type="text"
                value={arrayValue}
                placeholder="comma-separated values"
                onChange={(event) =>
                  setField(
                    key,
                    event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter((item) => item.length > 0),
                  )
                }
              />
            </label>
          );
        }

        if (propertySchema.type === "integer" || propertySchema.type === "number") {
          return (
            <label key={key} className="plugin-config-form__field">
              <span>{label}</span>
              <input
                type="number"
                value={typeof value === "number" ? value : ""}
                min={propertySchema.minimum}
                max={propertySchema.maximum}
                onChange={(event) =>
                  setField(key, event.target.value === "" ? undefined : Number(event.target.value))
                }
              />
            </label>
          );
        }

        if (propertySchema.type === "boolean") {
          return (
            <label
              key={key}
              className="plugin-config-form__field plugin-config-form__field--checkbox"
            >
              <input
                type="checkbox"
                checked={Boolean(value)}
                onChange={(event) => setField(key, event.target.checked)}
              />
              <span>{label}</span>
            </label>
          );
        }

        return (
          <label key={key} className="plugin-config-form__field">
            <span>{label}</span>
            <input
              type="text"
              value={typeof value === "string" ? value : ""}
              onChange={(event) => setField(key, event.target.value)}
            />
          </label>
        );
      })}
    </div>
  );
}
