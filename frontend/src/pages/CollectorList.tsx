import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { deleteCollector, deployCollector, listCollectors, stopCollectorDeployment } from "../api/collector";
import { listProjects } from "../api/project";
import { StatusBadge } from "../components/StatusBadge";
import type { Collector } from "../types/collector";
import type { Project } from "../types/project";
import "./Collector.css";

export function CollectorList() {
  const [collectors, setCollectors] = useState<Collector[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  function projectName(projectId: string): string {
    return projects.find((project) => project.id === projectId)?.name ?? "—";
  }

  async function refresh() {
    try {
      setCollectors(await listCollectors());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load collectors.");
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
        <h1>Collectors</h1>
        <Link className="button button--primary" to="/collectors/new">
          + New Collector
        </Link>
      </div>

      {error && <p className="collector-page__error">{error}</p>}

      {loading ? (
        <p>Loading...</p>
      ) : collectors.length === 0 ? (
        <div className="collector-page__empty">
          <p>No collectors yet. Create one to start ingesting telemetry.</p>
        </div>
      ) : (
        <div className="collector-card">
          <table className="collector-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Project</th>
                <th>Status</th>
                <th>Inputs</th>
                <th>Outputs</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {collectors.map((collector) => (
                <tr key={collector.id}>
                  <td>{collector.name}</td>
                  <td>{projectName(collector.project_id)}</td>
                  <td>
                    <StatusBadge status={collector.status} />
                  </td>
                  <td>{collector.inputs.map((input) => input.plugin_type).join(", ")}</td>
                  <td>{collector.outputs.map((output) => output.plugin_type).join(", ")}</td>
                  <td className="collector-table__actions">
                    {collector.status === "running" ? (
                      <button
                        className="button"
                        disabled={pendingId === collector.id}
                        onClick={() => withPending(collector.id, () => stopCollectorDeployment(collector.id))}
                      >
                        Stop
                      </button>
                    ) : (
                      <button
                        className="button"
                        disabled={pendingId === collector.id}
                        onClick={() => withPending(collector.id, () => deployCollector(collector.id))}
                      >
                        Deploy
                      </button>
                    )}
                    <button
                      className="button button--danger"
                      disabled={pendingId === collector.id}
                      onClick={() => withPending(collector.id, () => deleteCollector(collector.id))}
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
