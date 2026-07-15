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
import { colorAtIndex, initials } from "../utils/color";
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

  const runningCollectors = collectors.filter((collector) => collector.status === "running").length;
  const unhealthyCollectors = collectors.filter(
    (collector) => collector.status === "unhealthy" || collector.status === "error",
  ).length;
  const runningAutomaters = automaters.filter((automater) => automater.status === "running").length;
  const unhealthyAutomaters = automaters.filter(
    (automater) => automater.status === "unhealthy" || automater.status === "error",
  ).length;
  const enabledQueryRules = queryRules.filter((rule) => rule.enabled).length;
  const waitingQueryRules = queryRules.filter((rule) => rule.enabled && !rule.last_evaluated_at).length;
  const totalRules = automaters.reduce((sum, automater) => sum + automater.rules.length, 0);
  const enabledRealtimeRules = automaters.reduce(
    (sum, automater) => sum + automater.rules.filter((rule) => rule.enabled).length,
    0,
  );
  const totalDashboards = useMemo(
    () => Object.values(dashboardsByProject).reduce((sum, list) => sum + list.length, 0),
    [dashboardsByProject],
  );
  const totalUnresolved = useMemo(
    () => projects.reduce((sum, project) => sum + (unresolvedCounts[project.id] ?? 0), 0),
    [projects, unresolvedCounts],
  );

  function projectLink(projectId: string): string {
    const project = projects.find((p) => p.id === projectId);
    const dashboards = dashboardsByProject[projectId] ?? [];
    const target =
      (project?.default_dashboard_id && dashboards.find((d) => d.id === project.default_dashboard_id)) ??
      dashboards[0];
    return target ? `/dashboards/${target.id}` : "/dashboards/new";
  }

  const hasAutomation = automaters.length > 0 || queryRules.length > 0;

  function panelSuggestionLink(): string {
    for (const project of projects) {
      const dashboards = dashboardsByProject[project.id] ?? [];
      if (dashboards.length > 0) return `/dashboards/${dashboards[0].id}/panels/new`;
    }
    return "/dashboards/new";
  }

  const aiSuggestions = [
    {
      key: "realtime",
      label: "New Realtime Automation Suggestion",
      detail: "Stream telemetry looks ready for a rule — turn a live condition into an event.",
      to: "/automaters/new",
    },
    {
      key: "scheduled",
      label: "New Scheduled Rule Suggestion",
      detail: "Run a periodic SQL check across stored telemetry for slower-moving conditions.",
      to: "/query-rules/new",
    },
    {
      key: "panel",
      label: "New Dashboard Panel Suggestion",
      detail: "Surface a metric that's being collected but doesn't have a panel yet.",
      to: panelSuggestionLink(),
    },
  ];

  const tiles: Tile[] = [
    {
      key: "projects",
      to: "/projects",
      icon: ProjectIcon,
      label: "Projects",
      count: projects.length,
      sub: null,
      description: "Operational boundaries for deployments, dashboards, rules, and events.",
    },
    {
      key: "ingestion",
      to: "/collectors",
      icon: CollectorIcon,
      label: "Data Ingestion",
      count: collectors.length,
      sub: collectors.length > 0 ? `${runningCollectors} running` : null,
      description: "Collectors and Telegraf inputs that bring telemetry into TimescaleDB.",
    },
    {
      key: "automation",
      to: "/automaters",
      icon: AutomaterIcon,
      label: "Automation",
      count: totalRules,
      sub: totalRules > 0 ? `${enabledRealtimeRules} enabled · ${runningAutomaters} runtimes` : null,
      description: "Real-time rules that detect stream conditions and create events.",
    },
    {
      key: "scheduled",
      to: "/query-rules",
      icon: ScheduleIcon,
      label: "Scheduled Rules",
      count: queryRules.length,
      sub: queryRules.length > 0 ? `${enabledQueryRules} enabled` : null,
      description: "SQL rules for slower checks across tables, metrics, and time windows.",
    },
    {
      key: "dashboards",
      to: "/dashboards",
      icon: VisualizerIcon,
      label: "Dashboards",
      count: totalDashboards,
      sub: null,
      description: "Panels, variables, time ranges, and event overlays for telemetry.",
    },
  ];

  const healthItems = [
    {
      key: "collectors",
      label: "Collectors",
      status: unhealthyCollectors > 0 ? "Needs review" : collectors.length > 0 ? "Healthy" : "Not configured",
      detail:
        collectors.length > 0 ? `${runningCollectors}/${collectors.length} running` : "Create one to ingest telemetry",
      tone: unhealthyCollectors > 0 ? "danger" : collectors.length > 0 ? "success" : "muted",
    },
    {
      key: "automaters",
      label: "Automation runtimes",
      status: unhealthyAutomaters > 0 ? "Needs review" : automaters.length > 0 ? "Ready" : "Not configured",
      detail:
        automaters.length > 0
          ? `${runningAutomaters}/${automaters.length} running`
          : "Add real-time rules when streams exist",
      tone: unhealthyAutomaters > 0 ? "danger" : automaters.length > 0 ? "success" : "muted",
    },
    {
      key: "query-rules",
      label: "Scheduled checks",
      status: waitingQueryRules > 0 ? "Waiting to run" : queryRules.length > 0 ? "Scheduled" : "Not configured",
      detail:
        queryRules.length > 0 ? `${enabledQueryRules}/${queryRules.length} enabled` : "Use SQL for cross-metric checks",
      tone: waitingQueryRules > 0 ? "warning" : queryRules.length > 0 ? "success" : "muted",
    },
  ];

  const gettingStartedSteps = [
    {
      key: "project",
      label: "Create a project",
      done: projects.length > 0,
      to: projects.length > 0 ? "/projects" : "/projects/new",
    },
    {
      key: "ingestion",
      label: "Connect data ingestion",
      done: collectors.length > 0,
      to: collectors.length > 0 ? "/collectors" : "/collectors/new",
    },
    {
      key: "automation",
      label: "Set up automation or scheduled rules",
      done: hasAutomation,
      to: hasAutomation ? "/automaters" : "/automaters/new",
    },
    {
      key: "dashboards",
      label: "Build a dashboard",
      done: totalDashboards > 0,
      to: totalDashboards > 0 ? "/dashboards" : "/dashboards/new",
    },
  ];
  const completedSteps = gettingStartedSteps.filter((step) => step.done).length;
  const allStepsDone = completedSteps === gettingStartedSteps.length;

  return (
    <main className="page home-page">
      <section className="home-command">
        <div className="home-command__content">
          <p className="home-command__eyebrow">Operations overview</p>
          <h1>Telemetry, automation, events, and dashboards in one loop.</h1>
          <p className="home-command__copy">
            Ingest device data, visualize the stored signal, and let rules surface the states that
            need a human decision.
          </p>
          <div className="home-command__actions">
            <Link className="button button--primary" to="/projects/new">
              New Project
            </Link>
            <Link className="button" to="/collectors/new">
              New Collector
            </Link>
          </div>
        </div>
        <button type="button" className="home-command__promo" onClick={openCopilotPanel}>
          <CopilotIcon className="home-command__promo-icon" />
          <strong>AI-native ops</strong>
          <span>Ask your telemetry questions and get automation suggestions as you grow.</span>
        </button>
      </section>

      <div className="home-tiles">
        {tiles.map((tile) => (
          <Link key={tile.key} to={tile.to} className="home-tile">
            <div className="home-tile__topline">
              <tile.icon className="home-tile__icon" />
              {tile.sub && <span className="home-tile__sub">{tile.sub}</span>}
            </div>
            <div className="home-tile__main">
              <div className="home-tile__count">{loading ? "—" : tile.count}</div>
              <div className="home-tile__label">{tile.label}</div>
            </div>
            <p className="home-tile__desc">{tile.description}</p>
          </Link>
        ))}
        <div className={`home-tile home-tile--events ${totalUnresolved > 0 ? "home-tile--events-active" : ""}`}>
          <div className="home-tile__topline">
            <BellIcon className="home-tile__icon" />
          </div>
          <div className="home-tile__main">
            <div className="home-tile__count">{loading ? "—" : totalUnresolved}</div>
            <div className="home-tile__label">Active Events</div>
          </div>
          <p className="home-tile__desc">Unresolved matches across all projects.</p>
        </div>
      </div>

      {projects.length > 0 && (
        <div className="home-overview-grid">
          <section className="home-panel-card home-panel-card--wide">
            <div className="home-panel-card__header">
              <div>
                <h2>System Health</h2>
                <p>Live posture across ingestion, automation, and scheduled checks.</p>
              </div>
              <span
                className={`home-health-summary home-health-summary--${
                  unhealthyCollectors > 0 || unhealthyAutomaters > 0 ? "attention" : "clear"
                }`}
              >
                {unhealthyCollectors > 0 || unhealthyAutomaters > 0 ? "Attention" : "Clear"}
              </span>
            </div>
            <div className="home-health-list">
              {healthItems.map((item) => (
                <div key={item.key} className="home-health-item">
                  <div className="home-health-item__label">
                    <span className={`home-health-item__dot home-health-item__dot--${item.tone}`} />
                    <strong>{item.label}</strong>
                  </div>
                  <span className="home-health-item__detail">{item.detail}</span>
                  <em className="home-health-item__status">{item.status}</em>
                </div>
              ))}
            </div>
          </section>

          <section className="home-panel-card home-panel-card--projects">
            <div className="home-panel-card__header">
              <div>
                <h2>Projects</h2>
                <p>Collectors, rules, and dashboards per deployment.</p>
              </div>
              <Link className="home-section__link" to="/projects">
                Manage →
              </Link>
            </div>
            {loading ? (
              <p className="home-hint">Loading...</p>
            ) : (
              <div className="home-projects">
                {projects.map((project: Project, index: number) => {
                  const unresolved = unresolvedCounts[project.id] ?? 0;
                  const resourceCount =
                    (collectorsByProject.get(project.id) ?? 0) +
                    (automatersByProject.get(project.id) ?? 0) +
                    (queryRulesByProject.get(project.id) ?? 0) +
                    (dashboardsByProject[project.id]?.length ?? 0);
                  return (
                    <div key={project.id} className="home-project-card">
                      <div className="home-project-card__header">
                        <span className="home-project-card__badge" style={{ background: colorAtIndex(index) }}>
                          {initials(project.name)}
                        </span>
                        {unresolved > 0 && (
                          <span className="home-project-card__unresolved">{unresolved}</span>
                        )}
                      </div>
                      <Link to={projectLink(project.id)} className="home-project-card__name" title={project.name}>
                        {project.name}
                      </Link>
                      <span className="home-project-card__meta">
                        {resourceCount} resource{resourceCount === 1 ? "" : "s"}
                      </span>
                      <div className="home-project-card__footer">
                        <Link className="home-project-card__action" to={projectLink(project.id)}>
                          Dashboard
                        </Link>
                        <button
                          type="button"
                          className="home-project-card__action"
                          onClick={() => openProjectPanel(project.id)}
                        >
                          Events
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="home-panel-card home-panel-card--next">
            <div className="home-panel-card__header">
              <div>
                <h2>AI Suggestions</h2>
                <p>Recommended coverage based on your current telemetry.</p>
              </div>
              <CopilotIcon className="home-panel-card__icon" />
            </div>
            <div className="home-suggestions-list">
              {aiSuggestions.map((suggestion) => (
                <Link key={suggestion.key} className="home-next-action" to={suggestion.to} title={suggestion.detail}>
                  {suggestion.label}
                </Link>
              ))}
            </div>
          </section>
        </div>
      )}

      <section className="home-flow">
        <div className="home-flow__copy">
          <p className="home-command__eyebrow">Operating model</p>
          <h2>From raw streams to actionable events</h2>
          <p>
            IoTOps stays schema-first: collectors define telemetry entry points, dashboards query the
            stored signal, and automation turns important transitions into resolvable events.
          </p>
        </div>
        <div className="home-flow__steps">
          <Link to="/collectors" className="home-flow__step">
            <CollectorIcon />
            <strong>Ingest</strong>
            <span>MQTT, HTTP, Kafka, AMQP</span>
          </Link>
          <Link to="/dashboards" className="home-flow__step">
            <VisualizerIcon />
            <strong>Visualize</strong>
            <span>Panels, variables, overlays</span>
          </Link>
          <Link to="/automaters" className="home-flow__step">
            <AutomaterIcon />
            <strong>Automate</strong>
            <span>Stream rules and Celery events</span>
          </Link>
          <Link to="/query-rules" className="home-flow__step">
            <ScheduleIcon />
            <strong>Correlate</strong>
            <span>Scheduled SQL checks</span>
          </Link>
        </div>
      </section>

      <div className="home-panels">
        <div className="home-panel-card">
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
          {allStepsDone && <p className="home-getting-started__done">All set — every core feature is in use.</p>}
        </div>

        <div className="home-panel-card home-panel-card--copilot">
          <div className="home-panel-card__header">
            <h2>AI Co-pilot</h2>
            <span className="home-badge-soon">Coming soon</span>
          </div>
          <div className="home-copilot">
            <CopilotIcon className="home-copilot__icon" />
            <div className="home-copilot__body">
              <p className="home-copilot__lead">
                Ask it to explain a metric spike, draft a rule in plain English, or summarize what changed
                across your projects today — a persistent assistant that understands your telemetry,
                automation, dashboards, and event history.
              </p>
              <button type="button" className="button" onClick={openCopilotPanel}>
                Open Co-pilot
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
