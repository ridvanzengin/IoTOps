import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { deleteProject, listProjects } from "../api/project";
import type { Project } from "../types/project";
import "./Collector.css";

export function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

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

  async function handleDelete(id: string) {
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
                    <button
                      className="button button--danger"
                      disabled={pendingId === project.id}
                      onClick={() => handleDelete(project.id)}
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
