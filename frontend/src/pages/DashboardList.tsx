import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { deleteDashboard, listDashboards } from "../api/dashboard";
import { listProjects } from "../api/project";
import { CopilotIcon, MoreIcon } from "../components/icons";
import { useEvents } from "../context/EventsContext";
import type { Dashboard } from "../types/dashboard";
import type { Project } from "../types/project";
import "./Collector.css";

export function DashboardList() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const { openCopilotPanel } = useEvents();

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
      setDashboards(await listDashboards());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load dashboards.");
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

  async function handleDelete(id: string, name: string) {
    if (!window.confirm(`Delete dashboard "${name}"? This cannot be undone.`)) {
      return;
    }
    setPendingId(id);
    try {
      await deleteDashboard(id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete dashboard.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <h1>Dashboards</h1>
        <div className="collector-page__header-actions">
          <button
            type="button"
            className="button button--primary"
            onClick={() => openCopilotPanel("suggest-dashboard")}
          >
            <CopilotIcon width={16} height={16} />
            Ask AI
          </button>
          <Link className="button button--success" to="/dashboards/new">
            + New Dashboard
          </Link>
        </div>
      </div>

      {error && <p className="collector-page__error">{error}</p>}

      {loading ? (
        <p>Loading...</p>
      ) : dashboards.length === 0 ? (
        <div className="collector-page__empty">
          <p>No dashboards yet. Create one to start visualizing telemetry.</p>
        </div>
      ) : (
        <div className="collector-card">
          <div className="collector-table-wrapper">
          <table className="collector-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Project</th>
                <th>Panels</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {dashboards.map((dashboard) => (
                <tr key={dashboard.id}>
                  <td>
                    <Link className="collector-table__link" to={`/dashboards/${dashboard.id}`}>
                      {dashboard.name}
                    </Link>
                  </td>
                  <td>{projectName(dashboard.project_id)}</td>
                  <td>{dashboard.panels.length}</td>
                  <td className="collector-table__actions">
                    <div className="collector-table__actions-inner">
                    <div className="dropdown-menu">
                      <button
                        type="button"
                        className="dropdown-menu__trigger"
                        aria-label="Dashboard actions"
                        aria-expanded={openMenu === dashboard.id}
                        onClick={() => setOpenMenu((current) => (current === dashboard.id ? null : dashboard.id))}
                      >
                        <MoreIcon />
                      </button>
                      {openMenu === dashboard.id && (
                        <div className="dropdown-menu__list">
                          <button
                            type="button"
                            className="dropdown-menu__item dropdown-menu__item--danger"
                            disabled={pendingId === dashboard.id}
                            onClick={() => {
                              setOpenMenu(null);
                              handleDelete(dashboard.id, dashboard.name);
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
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
