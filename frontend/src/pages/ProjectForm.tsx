import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { createProject, getProject, updateProject } from "../api/project";
import "./Collector.css";

const AI_CONTEXT_MAX_LENGTH = 1000;

export function ProjectForm() {
  const navigate = useNavigate();
  const location = useLocation();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [aiContext, setAiContext] = useState("");
  const [defaultDashboardId, setDefaultDashboardId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const aiContextRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!id) return;
    getProject(id)
      .then((project) => {
        setName(project.name);
        setDescription(project.description);
        setAiContext(project.ai_context);
        setDefaultDashboardId(project.default_dashboard_id);
      })
      .catch(() => setError("Failed to load project."));
  }, [id]);

  // Lets a link elsewhere in the app (e.g. the Co-pilot's "add context"
  // nudge) land here with the ai_context field already focused, via
  // navigate(..., { state: { focusField: "ai_context" } }).
  useEffect(() => {
    const state = location.state as { focusField?: string } | null;
    if (state?.focusField === "ai_context") {
      aiContextRef.current?.focus();
      aiContextRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [location.state]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (id) {
        // Preserve default_dashboard_id -- this form doesn't edit it (set
        // via the activity bar's dashboard-switcher dropdown instead), so
        // re-send whatever was loaded rather than clobbering it with null.
        await updateProject(id, {
          name,
          description,
          ai_context: aiContext,
          default_dashboard_id: defaultDashboardId,
        });
      } else {
        await createProject({ name, description, ai_context: aiContext, default_dashboard_id: null });
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
        <label className="field" style={{ maxWidth: "none" }}>
          <span>AI Context (optional) — help the AI understand your data</span>
          <textarea
            ref={aiContextRef}
            value={aiContext}
            onChange={(event) => setAiContext(event.target.value.slice(0, AI_CONTEXT_MAX_LENGTH))}
            maxLength={AI_CONTEXT_MAX_LENGTH}
            rows={4}
            placeholder="e.g. val1 is coolant temperature in °C, sensor_a tracks primary shaft vibration"
          />
          <span className="wizard-panel__hint" style={{ textAlign: "right" }}>
            {aiContext.length}/{AI_CONTEXT_MAX_LENGTH}
          </span>
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
