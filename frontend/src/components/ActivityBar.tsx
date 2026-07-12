import { useNavigate } from "react-router-dom";
import { useEvents } from "../context/EventsContext";
import { CopilotIcon } from "./icons";
import "./ActivityBar.css";

// Deterministic project-id -> color, same fallback-avatar pattern
// Slack/GitHub use for entities with no dedicated icon/color field (no
// schema change on Project -- see iotops-workspace/ROADMAP.md's "Events
// sidebar polish" note). Distinct from the severity scale in index.css.
const PALETTE = [
  "#6d28d9",
  "#0f766e",
  "#b45309",
  "#be123c",
  "#1d4ed8",
  "#15803d",
  "#a21caf",
  "#0891b2",
];

function hashColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return PALETTE[hash % PALETTE.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

// Persistent, always-visible icon rail -- one icon per Project plus one
// for Co-pilot, reachable from every page (lives in the app root shell,
// not embedded in Dashboard pages). Each project's badge is its
// currently-unresolved-match count, not a lifetime total -- see
// iotops-workspace/ROADMAP.md's "Activity bar redesign" note.
export function ActivityBar() {
  const { projects, dashboardsByProject, unresolvedCounts, activePanel, openProjectPanel, openCopilotPanel, closePanel } =
    useEvents();
  const navigate = useNavigate();

  function handleProjectClick(projectId: string) {
    const isActive = activePanel?.kind === "project" && activePanel.projectId === projectId;
    if (isActive) {
      closePanel();
      return;
    }
    // Navigate to the project's default dashboard if one's set, else its
    // first dashboard, alongside opening the panel -- clicking a project
    // means "show me this project": both its visual dashboard and its
    // live events. A project with no dashboards yet just opens the panel.
    const project = projects.find((p) => p.id === projectId);
    const dashboards = dashboardsByProject[projectId] ?? [];
    const target =
      (project?.default_dashboard_id && dashboards.find((d) => d.id === project.default_dashboard_id)) ??
      dashboards[0];
    if (target) navigate(`/dashboards/${target.id}`);
    openProjectPanel(projectId);
  }

  return (
    <nav className="activity-bar">
      {projects.map((project) => {
        const count = unresolvedCounts[project.id] ?? 0;
        const isActive = activePanel?.kind === "project" && activePanel.projectId === project.id;
        return (
          <button
            key={project.id}
            type="button"
            className={`activity-bar__icon ${isActive ? "activity-bar__icon--active" : ""}`}
            style={{ background: hashColor(project.id) }}
            title={project.name}
            onClick={() => handleProjectClick(project.id)}
          >
            {initials(project.name)}
            {count > 0 && <span className="activity-bar__badge">{count}</span>}
          </button>
        );
      })}
      <div className="activity-bar__spacer" />
      <button
        type="button"
        className={`activity-bar__icon activity-bar__icon--copilot ${
          activePanel?.kind === "copilot" ? "activity-bar__icon--active" : ""
        }`}
        title="Co-pilot"
        onClick={() => (activePanel?.kind === "copilot" ? closePanel() : openCopilotPanel())}
      >
        <CopilotIcon className="activity-bar__copilot-icon" />
      </button>
    </nav>
  );
}
