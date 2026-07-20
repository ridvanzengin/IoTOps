import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { getDashboard, updateDashboard } from "../api/dashboard";
import { findVariableReferences, removeVariableAt } from "../utils/variables";
import type { Dashboard } from "../types/dashboard";
import "./Collector.css";

export function VariableList() {
  const { dashboardId } = useParams<{ dashboardId: string }>();
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingName, setPendingName] = useState<string | null>(null);

  async function refresh() {
    if (!dashboardId) return;
    try {
      setDashboard(await getDashboard(dashboardId));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardId]);

  async function handleDelete(name: string, index: number) {
    if (!dashboardId || !dashboard) return;
    const affected = findVariableReferences(dashboard, name, index);
    const warning =
      affected.length > 0
        ? `Deleting "$${name}" will break references in: ${affected.join(", ")}. Continue?`
        : `Delete variable "$${name}"?`;
    if (!window.confirm(warning)) return;

    setPendingName(name);
    try {
      const nextVariables = removeVariableAt(dashboard, index);
      await updateDashboard(dashboardId, {
        project_id: dashboard.project_id,
        name: dashboard.name,
        description: dashboard.description,
        variables: nextVariables,
        panels: dashboard.panels,
        layout: dashboard.layout,
      });
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete variable.");
    } finally {
      setPendingName(null);
    }
  }

  if (loading) {
    return (
      <main className="collector-page">
        <p>Loading...</p>
      </main>
    );
  }

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <div>
          <Link to={`/dashboards/${dashboardId}`} style={{ fontSize: 13, color: "var(--text)" }}>
            ← {dashboard?.name ?? "Dashboard"}
          </Link>
          <h1 style={{ marginTop: 4 }}>Variables</h1>
        </div>
        <Link className="button button--primary" to={`/dashboards/${dashboardId}/variables/new`}>
          + New Variable
        </Link>
      </div>

      {error && <p className="collector-page__error">{error}</p>}

      {!dashboard || dashboard.variables.length === 0 ? (
        <div className="collector-page__empty">
          <p>No variables yet. Create one to let viewers filter panels by a value they pick.</p>
        </div>
      ) : (
        <div className="collector-card">
          <div className="collector-table-wrapper">
          <table className="collector-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Label</th>
                <th>Value Source</th>
                <th>Predicate</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.variables.map((variable, index) => (
                <tr key={variable.name}>
                  <td>${variable.name}</td>
                  <td>{variable.label}</td>
                  <td>
                    {variable.table}.{variable.value_column}
                  </td>
                  <td>
                    {variable.predicate_column && variable.predicate_variable
                      ? `${variable.predicate_column} = $${variable.predicate_variable}`
                      : "—"}
                  </td>
                  <td className="collector-table__actions">
                    <div className="collector-table__actions-inner">
                    <Link className="button" to={`/dashboards/${dashboardId}/variables/${variable.name}/edit`}>
                      Edit
                    </Link>
                    <button
                      className="button button--danger"
                      disabled={pendingName === variable.name}
                      onClick={() => handleDelete(variable.name, index)}
                    >
                      Delete
                    </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </main>
  );
}
