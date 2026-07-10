import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { deleteAutomater, deployAutomater, listAutomaters, stopAutomaterDeployment } from "../api/automater";
import { listProjects } from "../api/project";
import { StatusBadge } from "../components/StatusBadge";
import type { Automater } from "../types/automater";
import type { Project } from "../types/project";
import "./Collector.css";

export function AutomaterList() {
  const [automaters, setAutomaters] = useState<Automater[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  function projectName(projectId: string): string {
    return projects.find((project) => project.id === projectId)?.name ?? "—";
  }

  async function refresh() {
    try {
      setAutomaters(await listAutomaters());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load automaters.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    listProjects()
      .then(setProjects)
      .catch(() => undefined);
  }, []);

  async function withPending(id: string, action: () => Promise<unknown>) {
    setPendingId(id);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <h1>Automaters</h1>
        <Link className="button button--primary" to="/automaters/new">
          + New Automater
        </Link>
      </div>

      {error && <p className="collector-page__error">{error}</p>}

      {loading ? (
        <p>Loading...</p>
      ) : automaters.length === 0 ? (
        <div className="collector-page__empty">
          <p>No automaters yet. Create one to start detecting events from your telemetry.</p>
        </div>
      ) : (
        <div className="collector-card">
          <table className="collector-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Project</th>
                <th>Status</th>
                <th>Rules</th>
                <th>Outputs</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {automaters.map((automater) => (
                <tr key={automater.id}>
                  <td>{automater.name}</td>
                  <td>{projectName(automater.project_id)}</td>
                  <td>
                    <StatusBadge status={automater.status} />
                  </td>
                  <td>{automater.rules.map((rule) => rule.name).join(", ")}</td>
                  <td>{automater.outputs.map((output) => output.plugin_type).join(", ")}</td>
                  <td className="collector-table__actions">
                    {automater.status === "running" ? (
                      <button
                        className="button"
                        disabled={pendingId === automater.id}
                        onClick={() => withPending(automater.id, () => stopAutomaterDeployment(automater.id))}
                      >
                        Stop
                      </button>
                    ) : (
                      <button
                        className="button"
                        disabled={pendingId === automater.id}
                        onClick={() => withPending(automater.id, () => deployAutomater(automater.id))}
                      >
                        Deploy
                      </button>
                    )}
                    <button
                      className="button button--danger"
                      disabled={pendingId === automater.id}
                      onClick={() => withPending(automater.id, () => deleteAutomater(automater.id))}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
