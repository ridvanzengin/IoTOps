import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { getDashboard, resolveVariableOptions, updateDashboard } from "../api/dashboard";
import { getTelemetrySchema } from "../api/telemetry";
import { SchemaBrowser } from "../components/SchemaBrowser";
import { findVariableReferences, removeVariableAt, resolveVariablesFrom } from "../utils/variables";
import type { Dashboard, Variable } from "../types/dashboard";
import type { TelemetryTableSchema } from "../types/telemetry";
import "./Collector.css";
import "./PanelBuilder.css";

function titleCase(value: string): string {
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export function VariableBuilder() {
  const { dashboardId, variableName } = useParams<{ dashboardId: string; variableName?: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(variableName);

  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [schema, setSchema] = useState<TelemetryTableSchema[]>([]);
  const [originalIndex, setOriginalIndex] = useState<number>(-1);

  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [label, setLabel] = useState("");
  const [labelTouched, setLabelTouched] = useState(false);
  const [table, setTable] = useState<string | null>(null);
  const [valueColumn, setValueColumn] = useState<string | null>(null);
  const [predicateColumn, setPredicateColumn] = useState<string | null>(null);
  const [predicateVariable, setPredicateVariable] = useState<string | null>(null);
  const [previewOptions, setPreviewOptions] = useState<string[] | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTelemetrySchema()
      .then(setSchema)
      .catch(() => setError("Failed to load schema."));
  }, []);

  useEffect(() => {
    if (!dashboardId) return;
    getDashboard(dashboardId)
      .then((loaded) => {
        setDashboard(loaded);
        if (variableName) {
          const index = loaded.variables.findIndex((v) => v.name === variableName);
          if (index === -1) {
            setError("Variable not found.");
            return;
          }
          const variable = loaded.variables[index];
          setOriginalIndex(index);
          setName(variable.name);
          setNameTouched(true);
          setLabel(variable.label);
          setLabelTouched(true);
          setTable(variable.table);
          setValueColumn(variable.value_column);
          setPredicateColumn(variable.predicate_column);
          setPredicateVariable(variable.predicate_variable);
        }
      })
      .catch(() => setError("Failed to load dashboard."));
  }, [dashboardId, variableName]);

  const earlierVariables = dashboard
    ? isEdit
      ? dashboard.variables.slice(0, originalIndex)
      : dashboard.variables
    : [];

  function selectValueColumn(colTable: string, column: string) {
    if (colTable !== table) {
      setPredicateColumn(null);
      setPredicateVariable(null);
    }
    setTable(colTable);
    setValueColumn(column);
    if (!nameTouched) setName(column);
    if (!labelTouched) setLabel(titleCase(column));
    setPreviewOptions(null);
  }

  // Only columns that some earlier variable already uses as its own
  // value_column (in this same table) are offered as predicates — that's
  // exactly what makes the binding unambiguous: picking "host" as the
  // predicate means "filtered by whichever variable already represents
  // mqtt_consumer.host," so there's nothing left to ask the user.
  const predicateColumnOptions = table
    ? (schema.find((t) => t.table === table)?.columns ?? [])
        .filter((column) => column.name !== valueColumn)
        .filter((column) => earlierVariables.some((v) => v.table === table && v.value_column === column.name))
    : [];

  function handlePredicateColumnChange(column: string) {
    const value = column || null;
    setPredicateColumn(value);
    setPredicateVariable(
      value ? (earlierVariables.find((v) => v.table === table && v.value_column === value)?.name ?? null) : null,
    );
    setPreviewOptions(null);
  }

  async function runPreview() {
    if (!dashboardId || !table || !valueColumn) return;
    setPreviewing(true);
    setError(null);
    try {
      const { values } = await resolveVariablesFrom(dashboardId, earlierVariables, 0, {});
      const result = await resolveVariableOptions(dashboardId, {
        table,
        value_column: valueColumn,
        predicate_column: predicateColumn,
        predicate_variable: predicateVariable,
        variable_values: values,
      });
      setPreviewOptions(result.options);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Preview query failed.");
      setPreviewOptions(null);
    } finally {
      setPreviewing(false);
    }
  }

  function buildVariable(): Variable {
    return {
      name,
      label,
      table: table!,
      value_column: valueColumn!,
      predicate_column: predicateColumn,
      predicate_variable: predicateColumn ? predicateVariable : null,
    };
  }

  async function handleSave() {
    if (!dashboardId || !dashboard || !table || !valueColumn) return;
    setError(null);

    const renamed = isEdit && name !== variableName;
    if (renamed) {
      const affected = findVariableReferences(dashboard, variableName!, originalIndex);
      if (
        affected.length > 0 &&
        !window.confirm(
          `Renaming "$${variableName}" to "$${name}" will break references in: ${affected.join(", ")}. Continue?`,
        )
      ) {
        return;
      }
    }

    setSaving(true);
    try {
      const variable = buildVariable();
      let nextVariables = isEdit
        ? dashboard.variables.map((v, i) => (i === originalIndex ? variable : v))
        : [...dashboard.variables, variable];

      if (renamed) {
        nextVariables = nextVariables.map((v, i) =>
          i !== originalIndex && v.predicate_variable === variableName
            ? { ...v, predicate_variable: name }
            : v,
        );
      }

      await updateDashboard(dashboardId, {
        project_id: dashboard.project_id,
        name: dashboard.name,
        description: dashboard.description,
        variables: nextVariables,
        panels: dashboard.panels,
        layout: dashboard.layout,
      });
      navigate(`/dashboards/${dashboardId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save variable.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!dashboardId || !dashboard || !variableName) return;
    const affected = findVariableReferences(dashboard, variableName, originalIndex);
    const warning =
      affected.length > 0
        ? `Deleting "$${variableName}" will break references in: ${affected.join(", ")}. Continue?`
        : `Delete variable "$${variableName}"?`;
    if (!window.confirm(warning)) return;

    setSaving(true);
    setError(null);
    try {
      const nextVariables = removeVariableAt(dashboard, originalIndex);
      await updateDashboard(dashboardId, {
        project_id: dashboard.project_id,
        name: dashboard.name,
        description: dashboard.description,
        variables: nextVariables,
        panels: dashboard.panels,
        layout: dashboard.layout,
      });
      navigate(`/dashboards/${dashboardId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete variable.");
    } finally {
      setSaving(false);
    }
  }

  const canSave =
    !saving &&
    name.trim() !== "" &&
    label.trim() !== "" &&
    table !== null &&
    valueColumn !== null &&
    (predicateColumn === null || predicateVariable !== null);

  return (
    <main className="collector-page panel-builder-page">
      <h1>{isEdit ? "Edit Variable" : "New Variable"}</h1>
      <p style={{ margin: "8px 0 24px", color: "var(--text)" }}>
        Pick a column from the schema browser as the variable's value source. Optionally pick a
        predicate column already used by an earlier variable to filter by it — this is how
        variables chain (e.g. narrow "Device" by the currently-selected "Project").
      </p>

      {error && <p className="collector-page__error">{error}</p>}

      <div className="panel-builder">
        <div className="panel-builder__column">
          <div className="wizard-panel">
            <h2 className="wizard-panel__title">Variable</h2>
            <label className="field">
              <span>Name</span>
              <input
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  setNameTouched(true);
                }}
                placeholder="hive_id"
              />
            </label>
            <label className="field">
              <span>Label</span>
              <input
                value={label}
                onChange={(event) => {
                  setLabel(event.target.value);
                  setLabelTouched(true);
                }}
                placeholder="Hive"
              />
            </label>

            <label className="field">
              <span>Value Source</span>
              <input
                readOnly
                value={table && valueColumn ? `${table}.${valueColumn}` : ""}
                placeholder="Click a column in the schema browser."
                style={{ background: "var(--bg-subtle)", cursor: "default" }}
              />
            </label>

            <label className="field">
              <span>Predicate (optional)</span>
              <select
                value={predicateColumn ?? ""}
                onChange={(event) => handlePredicateColumnChange(event.target.value)}
                disabled={!table || predicateColumnOptions.length === 0}
              >
                <option value="">None</option>
                {predicateColumnOptions.map((column) => (
                  <option key={column.name} value={column.name}>
                    {column.name}
                  </option>
                ))}
              </select>
              {table && predicateColumnOptions.length === 0 && (
                <span style={{ fontSize: 13, color: "var(--text)", fontWeight: 400 }}>
                  No earlier variables use a column from {table} yet.
                </span>
              )}
            </label>

            {predicateColumn && predicateVariable && (
              <p style={{ margin: 0, fontSize: 13, color: "var(--text)" }}>
                Filtered by ${predicateVariable}
              </p>
            )}

            <button
              type="button"
              className="button button--primary"
              style={{ marginTop: 16 }}
              onClick={runPreview}
              disabled={previewing || !table || !valueColumn}
            >
              {previewing ? "Running..." : "Run Preview"}
            </button>

            {previewOptions && (
              <div className="panel-builder__results">
                {previewOptions.length === 0 ? (
                  <p style={{ color: "var(--text)", fontSize: 13 }}>Query returned no values.</p>
                ) : (
                  <p style={{ fontSize: 13, color: "var(--text-h)" }}>{previewOptions.join(", ")}</p>
                )}
              </div>
            )}
          </div>

          <div className="wizard-actions">
            <button type="button" className="button" onClick={() => navigate(`/dashboards/${dashboardId}`)}>
              Cancel
            </button>
            <div style={{ display: "flex", gap: 8 }}>
              {isEdit && (
                <button type="button" className="button button--danger" onClick={handleDelete} disabled={saving}>
                  Delete
                </button>
              )}
              <button type="button" className="button button--success" onClick={handleSave} disabled={!canSave}>
                {saving ? "Saving..." : "Save Variable"}
              </button>
            </div>
          </div>
        </div>

        <div className="panel-builder__column">
          <div className="wizard-panel">
            <h2 className="wizard-panel__title">DB Schema</h2>
            <p className="wizard-panel__hint">Click a column to use it as the value source.</p>
            <SchemaBrowser
              onSelect={(token) => {
                const [colTable, column] = token.split(".");
                selectValueColumn(colTable, column);
              }}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
