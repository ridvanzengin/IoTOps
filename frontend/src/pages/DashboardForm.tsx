import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { createDashboard } from "../api/dashboard";
import { listProjects } from "../api/project";
import type { Project } from "../types/project";
import "./Collector.css";

export function DashboardForm() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [projectId, setProjectId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setError("Failed to load available projects."));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const dashboard = await createDashboard({
        project_id: projectId,
        name,
        description,
        variables: [],
        panels: [],
        layout: {},
      });
      navigate(`/dashboards/${dashboard.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create dashboard.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="collector-page collector-page--form">
      <h1>New Dashboard</h1>
      <p style={{ margin: "8px 0 24px", color: "var(--text)" }}>
        Pick the project whose telemetry this dashboard will visualize.
      </p>

      {error && <p className="collector-page__error">{error}</p>}

      <form className="wizard-panel" onSubmit={handleSubmit}>
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} required autoFocus />
        </label>
        <label className="field">
          <span>Description</span>
          <input value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>
        <label className="field">
          <span>Project</span>
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)} required>
            <option value="">Select a project</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        {projects.length === 0 && (
          <p className="collector-page__error" style={{ marginTop: 12 }}>
            No projects exist yet. Create one first.
          </p>
        )}

        <div className="wizard-actions">
          <button type="button" className="button" onClick={() => navigate("/dashboards")}>
            Cancel
          </button>
          <button
            type="submit"
            className="button button--primary"
            disabled={submitting || projects.length === 0}
          >
            {submitting ? "Creating..." : "Create Dashboard"}
          </button>
        </div>
      </form>
    </main>
  );
}
