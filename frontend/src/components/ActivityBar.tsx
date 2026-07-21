import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useEvents } from "../context/EventsContext";
import { useTheme } from "../context/ThemeContext";
import { useMediaQuery, MOBILE_QUERY } from "../hooks/useMediaQuery";
import { colorAtIndex, initials } from "../utils/color";
import { BellIcon, CopilotIcon, MoonIcon, SunIcon } from "./icons";
import "./ActivityBar.css";

// Desktop: persistent, always-visible icon rail -- one icon per Project
// plus one for Co-pilot, reachable from every page (lives in the app root
// shell, not embedded in Dashboard pages). Each project's badge is its
// currently-unresolved-match count, not a lifetime total -- see
// iotops-workspace/ROADMAP.md's "Activity bar redesign" note.
//
// Mobile: collapses into a single trigger (a bell badged with the total
// unresolved count across every project) that opens an off-canvas drawer
// mirroring Sidebar's own mobile pattern -- same reasoning as that
// component's mobile rework: a permanent 56px column has nowhere to go on
// a phone-width viewport. Unlike Sidebar, this collapses the Co-pilot
// entry in here too rather than keeping it always-visible outside the
// drawer -- Co-pilot already has its own always-reachable entry in the
// left nav (Sidebar.tsx's navItems), so this is a redundant second path
// to it, not the only one, and doesn't need the same one-tap priority.
export function ActivityBar() {
  const { projects, dashboardsByProject, unresolvedCounts, activePanel, openProjectPanel, openCopilotPanel, closePanel } =
    useEvents();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { pathname } = useLocation();

  // Same off-canvas-closes-on-navigate convention as Sidebar's own mobile
  // drawer -- otherwise this stays open over whatever page a project click
  // just navigated to.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const totalUnresolved = projects.reduce((sum, project) => sum + (unresolvedCounts[project.id] ?? 0), 0);

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

  if (isMobile) {
    return (
      <>
        <button
          type="button"
          className="activity-bar__mobile-trigger"
          onClick={() => setMobileOpen(true)}
          aria-label="Open activity menu"
        >
          <BellIcon className="activity-bar__mobile-trigger-icon" />
          {totalUnresolved > 0 && <span className="activity-bar__badge">{totalUnresolved}</span>}
        </button>
        {mobileOpen && <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} />}
        <nav className={`activity-bar--mobile${mobileOpen ? " activity-bar--mobile-open" : ""}`}>
          <div className="activity-bar__mobile-header">
            <strong>Activity</strong>
            <button
              type="button"
              className="activity-bar__mobile-close"
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
            >
              ×
            </button>
          </div>
          <button type="button" className="activity-bar__mobile-row" onClick={toggleTheme}>
            {theme === "dark" ? (
              <SunIcon className="activity-bar__mobile-row-icon" />
            ) : (
              <MoonIcon className="activity-bar__mobile-row-icon" />
            )}
            <span>{theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}</span>
          </button>
          {projects.map((project, index) => {
            const count = unresolvedCounts[project.id] ?? 0;
            const isActive = activePanel?.kind === "project" && activePanel.projectId === project.id;
            return (
              <button
                key={project.id}
                type="button"
                className={`activity-bar__mobile-row${isActive ? " activity-bar__mobile-row--active" : ""}`}
                onClick={() => handleProjectClick(project.id)}
              >
                <span className="activity-bar__mobile-row-badge" style={{ background: colorAtIndex(index) }}>
                  {initials(project.name)}
                </span>
                <span className="activity-bar__mobile-row-label">{project.name}</span>
                {count > 0 && <span className="activity-bar__badge activity-bar__badge--inline">{count}</span>}
              </button>
            );
          })}
          <button
            type="button"
            className={`activity-bar__mobile-row${activePanel?.kind === "copilot" ? " activity-bar__mobile-row--active" : ""}`}
            onClick={() => (activePanel?.kind === "copilot" ? closePanel() : openCopilotPanel())}
          >
            <CopilotIcon className="activity-bar__mobile-row-icon" />
            <span>Co-pilot</span>
          </button>
        </nav>
      </>
    );
  }

  return (
    <nav className="activity-bar">
      <button
        type="button"
        className="activity-bar__icon activity-bar__icon--theme"
        title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        aria-pressed={theme === "light"}
        onClick={toggleTheme}
      >
        {theme === "dark" ? <SunIcon className="activity-bar__theme-icon" /> : <MoonIcon className="activity-bar__theme-icon" />}
      </button>
      {projects.map((project, index) => {
        const count = unresolvedCounts[project.id] ?? 0;
        const isActive = activePanel?.kind === "project" && activePanel.projectId === project.id;
        return (
          <button
            key={project.id}
            type="button"
            className={`activity-bar__icon ${isActive ? "activity-bar__icon--active" : ""}`}
            style={{ background: colorAtIndex(index) }}
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
