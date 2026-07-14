import { useEffect, useMemo, useState } from "react";
import type { ComponentType, SVGProps } from "react";
import { Link } from "react-router-dom";
import { listAutomaters } from "../api/automater";
import { listCollectors } from "../api/collector";
import { listQueryRules } from "../api/queryRule";
import {
  AutomaterIcon,
  BellIcon,
  CollectorIcon,
  CopilotIcon,
  ProjectIcon,
  ScheduleIcon,
  VisualizerIcon,
} from "../components/icons";
import { useEvents } from "../context/EventsContext";
import { hashColor, initials } from "../utils/color";
import type { Automater } from "../types/automater";
import type { Collector } from "../types/collector";
import type { Project } from "../types/project";
import type { QueryRule } from "../types/queryRule";
import "./Home.css";

function countByProject<T extends { project_id: string }>(items: T[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const item of items) map.set(item.project_id, (map.get(item.project_id) ?? 0) + 1);
  return map;
}

interface Tile {
  key: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  count: number;
  sub: string | null;
  description: string;
}

export function Home() {
  const { projects, dashboardsByProject, unresolvedCounts, openProjectPanel, openCopilotPanel } = useEvents();
  const [collectors, setCollectors] = useState<Collector[]>([]);
  const [automaters, setAutomaters] = useState<Automater[]>([]);
  const [queryRules, setQueryRules] = useState<QueryRule[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([listCollectors(), listAutomaters(), listQueryRules()])
      .then(([fetchedCollectors, fetchedAutomaters, fetchedQueryRules]) => {
        setCollectors(fetchedCollectors);
        setAutomaters(fetchedAutomaters);
        setQueryRules(fetchedQueryRules);
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  const collectorsByProject = useMemo(() => countByProject(collectors), [collectors]);
  const automatersByProject = useMemo(() => countByProject(automaters), [automaters]);
  const queryRulesByProject = useMemo(() => countByProject(queryRules), [queryRules]);

  const runningCollectors = collectors.filter((c) => c.status === "running").length;
  const runningAutomaters = automaters.filter((a) => a.status === "running").length;
  const enabledQueryRules = queryRules.filter((q) => q.enabled).length;
  const totalRules = automaters.reduce((sum, a) => sum + a.rules.length, 0);
  const totalDashboards = useMemo(
    () => Object.values(dashboardsByProject).reduce((sum, list) => sum + list.length, 0),
    [dashboardsByProject],
  );
  // Summed only over projects that still exist -- unresolvedCounts itself
  // is keyed by whatever project_id happens to be stamped on an Event
  // document, which outlives a deleted Project (nothing cascade-deletes
  // its old events). Object.values(unresolvedCounts) would silently
  // include those orphaned counts and never agree with what's shown below
  // per-project.
  const totalUnresolved = useMemo(
    () => projects.reduce((sum, project) => sum + (unresolvedCounts[project.id] ?? 0), 0),
    [projects, unresolvedCounts],
  );

  // Same "default dashboard, else its first" preference ActivityBar's own
  // project-click handler uses -- kept in sync deliberately, since this is
  // the same underlying action (open this project's visual home).
  function projectLink(projectId: string): string {
    const project = projects.find((p) => p.id === projectId);
    const dashboards = dashboardsByProject[projectId] ?? [];
    const target =
      (project?.default_dashboard_id && dashboards.find((d) => d.id === project.default_dashboard_id)) ??
      dashboards[0];
    return target ? `/dashboards/${target.id}` : "/dashboards/new";
  }

  const tiles: Tile[] = [
    {
      key: "projects",
      to: "/projects",
      icon: ProjectIcon,
      label: "Projects",
      count: projects.length,
      sub: null,
      description: "Group Data Ingestion, Automation, and Dashboards per deployment.",
    },
    {
      key: "ingestion",
      to: "/collectors",
      icon: CollectorIcon,
      label: "Data Ingestion",
      count: collectors.length,
      sub: collectors.length > 0 ? `${runningCollectors} running` : null,
      description: "Telegraf collectors pulling telemetry from your devices.",
    },
    {
      key: "automation",
      to: "/automaters",
      icon: AutomaterIcon,
      label: "Automation",
      count: automaters.length,
      sub: totalRules > 0 ? `${totalRules} rule${totalRules === 1 ? "" : "s"}, ${runningAutomaters} running` : null,
      description: "Real-time rules that detect conditions as data streams in.",
    },
    {
      key: "scheduled",
      to: "/query-rules",
      icon: ScheduleIcon,
      label: "Scheduled Rules",
      count: queryRules.length,
      sub: queryRules.length > 0 ? `${enabledQueryRules} enabled` : null,
      description: "SQL-based rules re-evaluated on a schedule.",
    },
    {
      key: "dashboards",
      to: "/dashboards",
      icon: VisualizerIcon,
      label: "Dashboards",
      count: totalDashboards,
      sub: null,
      description: "Visualize telemetry and event history.",
    },
  ];

  const hasAutomation = automaters.length > 0 || queryRules.length > 0;
  const gettingStartedSteps = [
    {
      key: "project",
      label: "Create a project",
      done: projects.length > 0,
      to: projects.length > 0 ? "/projects" : "/projects/new",
    },
    {
      key: "ingestion",
      label: "Connect Data Ingestion",
      done: collectors.length > 0,
      to: collectors.length > 0 ? "/collectors" : "/collectors/new",
    },
    {
      key: "automation",
      label: "Set up Automation or Scheduled Rules",
      done: hasAutomation,
      to: hasAutomation ? "/automaters" : "/automaters/new",
    },
    {
      key: "dashboards",
      label: "Build a Dashboard",
      done: totalDashboards > 0,
      to: totalDashboards > 0 ? "/dashboards" : "/dashboards/new",
    },
  ];
  const completedSteps = gettingStartedSteps.filter((step) => step.done).length;
  const allStepsDone = completedSteps === gettingStartedSteps.length;

  const copilotCard = (
    <div className="home-panel-card" key="copilot">
      <div className="home-panel-card__header">
        <h2>AI Co-pilot</h2>
        <span className="home-badge-soon">Coming soon</span>
      </div>
      <div className="home-copilot">
        <CopilotIcon className="home-copilot__icon" />
        <div className="home-copilot__body">
          <p className="home-copilot__lead">
            A persistent assistant that understands your telemetry, rules, and events.
          </p>
          <ul className="home-copilot__features">
            <li>Ask questions over your event history and telemetry trends</li>
            <li>Get suggested Automation rules from patterns it spots in your data</li>
            <li>Get suggested Dashboard panels for the schema you're working with</li>
          </ul>
          <button type="button" className="button" onClick={openCopilotPanel}>
            Open Co-pilot
          </button>
        </div>
      </div>
    </div>
  );

  const gettingStartedCard = (
    <div className="home-panel-card" key="getting-started">
      <div className="home-panel-card__header">
        <h2>Getting Started</h2>
        <span className="home-panel-card__progress">
          {completedSteps}/{gettingStartedSteps.length}
        </span>
      </div>
      <ul className="home-getting-started__list">
        {gettingStartedSteps.map((step) =>
          step.done ? (
            <li key={step.key}>
              <span className="home-getting-started__row home-getting-started__row--done">
                <span className="home-getting-started__check">✓</span>
                {step.label}
              </span>
            </li>
          ) : (
            <li key={step.key}>
              <Link to={step.to} className="home-getting-started__row">
                <span className="home-getting-started__check" />
                {step.label}
              </Link>
            </li>
          ),
        )}
      </ul>
      {allStepsDone && <p className="home-getting-started__done">All set — you're using every part of IoTOps.</p>}
    </div>
  );

  return (
    <main className="page">
      <div className="home-tiles">
        {tiles.map((tile) => (
          <Link key={tile.key} to={tile.to} className="home-tile">
            <tile.icon className="home-tile__icon" />
            <div className="home-tile__count">{loading ? "—" : tile.count}</div>
            <div className="home-tile__label">{tile.label}</div>
            {tile.sub && <div className="home-tile__sub">{tile.sub}</div>}
            <p className="home-tile__desc">{tile.description}</p>
          </Link>
        ))}
        <div
          className={`home-tile home-tile--events ${totalUnresolved > 0 ? "home-tile--events-active" : ""}`}
        >
          <BellIcon className="home-tile__icon" />
          <div className="home-tile__count">{loading ? "—" : totalUnresolved}</div>
          <div className="home-tile__label">Active Events</div>
          <p className="home-tile__desc">Unresolved matches across all projects.</p>
        </div>
      </div>

      <section className="home-section">
        <div className="home-section__header">
          <h2>Projects</h2>
          <Link className="home-section__link" to="/projects">
            Manage projects →
          </Link>
        </div>
        {loading ? (
          <p className="home-hint">Loading...</p>
        ) : projects.length === 0 ? (
          <div className="home-empty">
            <p>
              No projects yet. A project groups a Collector with its Automaters, Scheduled Rules, and
              Dashboards.
            </p>
            <Link className="button button--primary" to="/projects/new">
              + New Project
            </Link>
          </div>
        ) : (
          <div className="home-projects">
            {projects.map((project: Project) => {
              const unresolved = unresolvedCounts[project.id] ?? 0;
              return (
                <div key={project.id} className="home-project-card">
                  <div className="home-project-card__header">
                    <span className="home-project-card__badge" style={{ background: hashColor(project.id) }}>
                      {initials(project.name)}
                    </span>
                    <Link to={projectLink(project.id)} className="home-project-card__name" title={project.name}>
                      {project.name}
                    </Link>
                    {unresolved > 0 && (
                      <span className="home-project-card__unresolved">{unresolved} active</span>
                    )}
                  </div>
                  {project.description && <p className="home-project-card__desc">{project.description}</p>}
                  <div className="home-project-card__stats">
                    <span>{collectorsByProject.get(project.id) ?? 0} collectors</span>
                    <span>{automatersByProject.get(project.id) ?? 0} automaters</span>
                    <span>{queryRulesByProject.get(project.id) ?? 0} scheduled</span>
                    <span>{dashboardsByProject[project.id]?.length ?? 0} dashboards</span>
                  </div>
                  <div className="home-project-card__footer">
                    <Link className="button" to={projectLink(project.id)}>
                      Open Dashboard
                    </Link>
                    <button type="button" className="button" onClick={() => openProjectPanel(project.id)}>
                      View Events
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <div className="home-panels">
        {gettingStartedCard}
        {copilotCard}
      </div>
    </main>
  );
}
