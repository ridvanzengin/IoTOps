import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { deleteCollector, deployCollector, listCollectors, stopCollectorDeployment } from "../api/collector";
import { listProjects } from "../api/project";
import { MoreIcon } from "../components/icons";
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
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (!(event.target instanceof Element) || !event.target.closest(".dropdown-menu")) {
        setOpenMenu(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
        <h1>Data Ingestion</h1>
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
                    <div className="dropdown-menu">
                      <button
                        type="button"
                        className="dropdown-menu__trigger"
                        aria-label="Collector actions"
                        aria-expanded={openMenu === collector.id}
                        onClick={() => setOpenMenu((current) => (current === collector.id ? null : collector.id))}
                      >
                        <MoreIcon />
                      </button>
                      {openMenu === collector.id && (
                        <div className="dropdown-menu__list">
                          <button
                            type="button"
                            className="dropdown-menu__item dropdown-menu__item--danger"
                            disabled={pendingId === collector.id}
                            onClick={() => {
                              setOpenMenu(null);
                              withPending(collector.id, () => deleteCollector(collector.id));
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
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
