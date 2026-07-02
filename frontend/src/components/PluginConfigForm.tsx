import type { JsonSchema, JsonSchemaProperty } from "../types/plugin";

interface PluginConfigFormProps {
  schema: JsonSchema;
  configuration: Record<string, unknown>;
  onChange: (configuration: Record<string, unknown>) => void;
}

function Field({
  fieldKey,
  propertySchema,
  value,
  required,
  onChange,
}: {
  fieldKey: string;
  propertySchema: JsonSchemaProperty;
  value: unknown;
  required: boolean;
  onChange: (value: unknown) => void;
}) {
  const label = required ? `${propertySchema.title ?? fieldKey} *` : (propertySchema.title ?? fieldKey);

  if (propertySchema.enum) {
    return (
      <label className="plugin-config-form__field">
        <span>{label}</span>
        <select
          value={String(value ?? "")}
          onChange={(event) => {
            const raw = event.target.value;
            const numeric = Number(raw);
            onChange(propertySchema.type === "integer" && !Number.isNaN(numeric) ? numeric : raw);
          }}
        >
          {propertySchema.enum.map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (propertySchema.type === "array") {
    const arrayValue = Array.isArray(value) ? value.join(", ") : "";
    return (
      <label className="plugin-config-form__field">
        <span>{label}</span>
        <input
          type="text"
          value={arrayValue}
          placeholder="comma-separated values"
          onChange={(event) =>
            onChange(
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

  if (propertySchema.type === "object") {
    return (
      <label className="plugin-config-form__field plugin-config-form__field--wide">
        <span>{label} (JSON)</span>
        <textarea
          rows={3}
          defaultValue={JSON.stringify(value ?? propertySchema.default ?? {}, null, 2)}
          onBlur={(event) => {
            try {
              onChange(JSON.parse(event.target.value));
            } catch {
              // Leave the last valid value in state until the JSON parses.
            }
          }}
        />
      </label>
    );
  }

  if (propertySchema.type === "integer" || propertySchema.type === "number") {
    return (
      <label className="plugin-config-form__field">
        <span>{label}</span>
        <input
          type="number"
          value={typeof value === "number" ? value : ""}
          min={propertySchema.minimum}
          max={propertySchema.maximum}
          onChange={(event) =>
            onChange(event.target.value === "" ? undefined : Number(event.target.value))
          }
        />
      </label>
    );
  }

  if (propertySchema.type === "boolean") {
    return (
      <label className="plugin-config-form__field plugin-config-form__field--checkbox">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{label}</span>
      </label>
    );
  }

  return (
    <label className="plugin-config-form__field">
      <span>{label}</span>
      <input
        type={fieldKey === "password" ? "password" : "text"}
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export function PluginConfigForm({ schema, configuration, onChange }: PluginConfigFormProps) {
  const properties = Object.entries(schema.properties ?? {});
  const required = new Set(schema.required ?? []);
  const primary = properties.filter(([, propertySchema]) => !propertySchema.advanced);
  const advanced = properties.filter(([, propertySchema]) => propertySchema.advanced);

  function setField(key: string, value: unknown) {
    onChange({ ...configuration, [key]: value });
  }

  return (
    <div>
      <div className="plugin-config-form">
        {primary.map(([key, propertySchema]) => (
          <Field
            key={key}
            fieldKey={key}
            propertySchema={propertySchema}
            value={configuration[key]}
            required={required.has(key)}
            onChange={(value) => setField(key, value)}
          />
        ))}
      </div>

      {advanced.length > 0 && (
        <details className="plugin-config-form__advanced">
          <summary>Advanced options</summary>
          <div className="plugin-config-form">
            {advanced.map(([key, propertySchema]) => (
              <Field
                key={key}
                fieldKey={key}
                propertySchema={propertySchema}
                value={configuration[key]}
                required={required.has(key)}
                onChange={(value) => setField(key, value)}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
