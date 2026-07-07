import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { createProject, getProject, updateProject } from "../api/project";
import "./Collector.css";

export function ProjectForm() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!id) return;
    getProject(id)
      .then((project) => {
        setName(project.name);
        setDescription(project.description);
      })
      .catch(() => setError("Failed to load project."));
  }, [id]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (id) {
        await updateProject(id, { name, description });
      } else {
        await createProject({ name, description });
      }
      navigate("/projects");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save project.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="collector-page collector-page--form">
      <h1>{isEdit ? "Edit Project" : "New Project"}</h1>
      <p style={{ margin: "8px 0 24px", color: "var(--text)" }}>
        Projects group a Collector with its Automaters and Dashboards.
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

        <div className="wizard-actions">
          <button type="button" className="button" onClick={() => navigate("/projects")}>
            Cancel
          </button>
          <button type="submit" className="button button--primary" disabled={submitting}>
            {submitting ? "Saving..." : isEdit ? "Save Changes" : "Create Project"}
          </button>
        </div>
      </form>
    </main>
  );
}
