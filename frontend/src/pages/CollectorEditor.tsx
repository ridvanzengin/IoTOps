import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { createCollector } from "../api/collector";
import { listPlugins } from "../api/plugin";
import { PluginConfigForm } from "../components/PluginConfigForm";
import type {
  CollectorInputPayload,
  InputPluginPayload,
  OutputPluginPayload,
  ProcessorPluginPayload,
} from "../types/collector";
import type { Plugin, PluginCategory } from "../types/plugin";
import "./Collector.css";

function pluginByType(plugins: Plugin[], pluginType: string): Plugin | undefined {
  return plugins.find((plugin) => plugin.name === pluginType);
}

interface PluginRowsProps<T extends { plugin_type: string; enabled: boolean; configuration: Record<string, unknown> }> {
  title: string;
  category: PluginCategory;
  availablePlugins: Plugin[];
  rows: T[];
  onChange: (rows: T[]) => void;
  makeRow: (plugin: Plugin) => T;
  renderExtraFields?: (row: T, update: (changes: Partial<T>) => void) => ReactNode;
}

function PluginRows<T extends { plugin_type: string; enabled: boolean; configuration: Record<string, unknown> }>({
  title,
  category,
  availablePlugins,
  rows,
  onChange,
  makeRow,
  renderExtraFields,
}: PluginRowsProps<T>) {
  const options = availablePlugins.filter((plugin) => plugin.category === category);

  function addRow() {
    if (options.length === 0) return;
    onChange([...rows, makeRow(options[0])]);
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  function updateRow(index: number, changes: Partial<T>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  }

  return (
    <fieldset className="collector-editor__section">
      <legend>{title}</legend>
      {rows.map((row, index) => {
        const plugin = pluginByType(options, row.plugin_type);
        return (
          <div key={index} className="collector-editor__plugin-row">
            <div className="collector-editor__plugin-row-header">
              <select
                value={row.plugin_type}
                onChange={(event) =>
                  updateRow(index, {
                    plugin_type: event.target.value,
                    configuration: {},
                  } as Partial<T>)
                }
              >
                {options.map((option) => (
                  <option key={option.name} value={option.name}>
                    {option.name}
                  </option>
                ))}
              </select>
              {renderExtraFields?.(row, (changes) => updateRow(index, changes))}
              <label className="collector-editor__enabled">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(event) => updateRow(index, { enabled: event.target.checked } as Partial<T>)}
                />
                Enabled
              </label>
              <button type="button" onClick={() => removeRow(index)}>
                Remove
              </button>
            </div>
            {plugin && (
              <PluginConfigForm
                schema={plugin.configuration_schema}
                configuration={row.configuration}
                onChange={(configuration) => updateRow(index, { configuration } as Partial<T>)}
              />
            )}
          </div>
        );
      })}
      <button type="button" onClick={addRow} disabled={options.length === 0}>
        Add {title.slice(0, -1)}
      </button>
    </fieldset>
  );
}

export function CollectorEditor() {
  const navigate = useNavigate();
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [inputs, setInputs] = useState<InputPluginPayload[]>([]);
  const [processors, setProcessors] = useState<ProcessorPluginPayload[]>([]);
  const [outputs, setOutputs] = useState<OutputPluginPayload[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listPlugins()
      .then(setPlugins)
      .catch(() => setError("Failed to load available plugins."));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (inputs.length === 0 || outputs.length === 0) {
      setError("A collector needs at least one input and one output.");
      return;
    }

    const payload: CollectorInputPayload = {
      name,
      description,
      enabled: true,
      inputs,
      processors,
      outputs,
    };

    setSubmitting(true);
    try {
      await createCollector(payload);
      navigate("/collectors");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create collector.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="collector-page">
      <h1>New Collector</h1>
      {error && <p className="collector-page__error">{error}</p>}

      <form className="collector-editor" onSubmit={handleSubmit}>
        <label className="collector-editor__field">
          <span>Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label className="collector-editor__field">
          <span>Description</span>
          <input value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>

        <PluginRows
          title="Inputs"
          category="input"
          availablePlugins={plugins}
          rows={inputs}
          onChange={setInputs}
          makeRow={(plugin) => ({ plugin_type: plugin.name, name: plugin.name, enabled: true, configuration: {} })}
          renderExtraFields={(row, update) => (
            <input
              className="collector-editor__name-field"
              value={row.name}
              placeholder="instance name"
              onChange={(event) => update({ name: event.target.value })}
            />
          )}
        />

        <PluginRows
          title="Processors"
          category="processor"
          availablePlugins={plugins}
          rows={processors}
          onChange={setProcessors}
          makeRow={(plugin) => ({ plugin_type: plugin.name, enabled: true, configuration: {} })}
        />

        <PluginRows
          title="Outputs"
          category="output"
          availablePlugins={plugins}
          rows={outputs}
          onChange={setOutputs}
          makeRow={(plugin) => ({ plugin_type: plugin.name, enabled: true, configuration: {} })}
        />

        <button type="submit" className="button" disabled={submitting}>
          {submitting ? "Creating..." : "Create Collector"}
        </button>
      </form>
    </main>
  );
}
