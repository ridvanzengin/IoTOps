import type { ReactNode } from "react";
import { PluginConfigForm } from "./PluginConfigForm";
import { defaultsFromSchema } from "../utils/jsonSchema";
import type { Plugin, PluginCategory } from "../types/plugin";

export function pluginByType(plugins: Plugin[], pluginType: string): Plugin | undefined {
  return plugins.find((plugin) => plugin.name === pluginType);
}

interface PluginRowsProps<
  T extends { plugin_type: string; enabled: boolean; configuration: Record<string, unknown> },
> {
  category: PluginCategory;
  availablePlugins: Plugin[];
  rows: T[];
  onChange: (rows: T[]) => void;
  makeRow: (plugin: Plugin) => T;
  renderExtraFields?: (row: T, update: (changes: Partial<T>) => void) => ReactNode;
}

export function PluginRows<
  T extends { plugin_type: string; enabled: boolean; configuration: Record<string, unknown> },
>({ category, availablePlugins, rows, onChange, makeRow, renderExtraFields }: PluginRowsProps<T>) {
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
    <div>
      {rows.map((row, index) => {
        const plugin = pluginByType(options, row.plugin_type);
        return (
          <div key={index} className="plugin-row">
            <div className="plugin-row__header">
              <select
                value={row.plugin_type}
                onChange={(event) => {
                  const nextPlugin = pluginByType(options, event.target.value);
                  updateRow(index, {
                    plugin_type: event.target.value,
                    configuration: nextPlugin ? defaultsFromSchema(nextPlugin.configuration_schema) : {},
                  } as Partial<T>);
                }}
              >
                {options.map((option) => (
                  <option key={option.name} value={option.name}>
                    {option.name}
                  </option>
                ))}
              </select>
              {renderExtraFields?.(row, (changes) => updateRow(index, changes))}
              <div className="plugin-row__spacer" />
              <label className="plugin-row__enabled">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(event) => updateRow(index, { enabled: event.target.checked } as Partial<T>)}
                />
                Enabled
              </label>
              <button type="button" className="button button--danger" onClick={() => removeRow(index)}>
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
      <button type="button" className="button" onClick={addRow} disabled={options.length === 0}>
        + Add {category}
      </button>
      {options.length === 0 && (
        <p className="collector-page__error" style={{ marginTop: 12 }}>
          No {category} plugins are registered yet.
        </p>
      )}
    </div>
  );
}
