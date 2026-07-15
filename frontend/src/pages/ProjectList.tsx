import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { deleteProject, listProjects } from "../api/project";
import { MoreIcon } from "../components/icons";
import type { Project } from "../types/project";
import "./Collector.css";

export function ProjectList() {
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

  async function refresh() {
    try {
      setProjects(await listProjects());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleDelete(id: string, name: string) {
    if (
      !window.confirm(
        `Delete project "${name}" and everything in it — its collectors, automations, scheduled rules, and dashboards? This cannot be undone.`,
      )
    )
      return;
    setPendingId(id);
    try {
      await deleteProject(id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete project.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <h1>Projects</h1>
        <Link className="button button--primary" to="/projects/new">
          + New Project
        </Link>
      </div>

      {error && <p className="collector-page__error">{error}</p>}

      {loading ? (
        <p>Loading...</p>
      ) : projects.length === 0 ? (
        <div className="collector-page__empty">
          <p>No projects yet. Create one to group its collectors, automaters, and dashboards.</p>
        </div>
      ) : (
        <div className="collector-card">
          <table className="collector-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.id}>
                  <td>{project.name}</td>
                  <td>{project.description}</td>
                  <td className="collector-table__actions">
                    <Link className="button" to={`/projects/${project.id}/edit`}>
                      Edit
                    </Link>
                    <div className="dropdown-menu">
                      <button
                        type="button"
                        className="dropdown-menu__trigger"
                        aria-label="Project actions"
                        aria-expanded={openMenu === project.id}
                        onClick={() => setOpenMenu((current) => (current === project.id ? null : project.id))}
                      >
                        <MoreIcon />
                      </button>
                      {openMenu === project.id && (
                        <div className="dropdown-menu__list">
                          <button
                            type="button"
                            className="dropdown-menu__item dropdown-menu__item--danger"
                            disabled={pendingId === project.id}
                            onClick={() => {
                              setOpenMenu(null);
                              handleDelete(project.id, project.name);
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
