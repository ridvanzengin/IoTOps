import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listDashboards } from "../api/dashboard";
import { getEventCounts, listEvents } from "../api/event";
import { fetchHealth } from "../api/health";
import { listProjects } from "../api/project";
import type { Dashboard } from "../types/dashboard";
import type { Event, EventRuleCount } from "../types/event";
import type { Project } from "../types/project";
import "./Home.css";

function relativeTime(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function Home() {
  const [backendStatus, setBackendStatus] = useState<"checking" | "ok" | "unreachable">("checking");
  const [projects, setProjects] = useState<Project[]>([]);
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [counts, setCounts] = useState<EventRuleCount[]>([]);
  const [latestEvents, setLatestEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchHealth()
      .then((health) => setBackendStatus(health.status === "ok" ? "ok" : "unreachable"))
      .catch(() => setBackendStatus("unreachable"));

    Promise.all([listProjects(), listDashboards(), getEventCounts(), listEvents(undefined, 5)])
      .then(([fetchedProjects, fetchedDashboards, fetchedCounts, fetchedLatest]) => {
        setProjects(fetchedProjects);
        setDashboards(fetchedDashboards);
        setCounts(fetchedCounts);
        setLatestEvents(fetchedLatest);
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  // A project's events panel (opened via the activity bar, see
  // EventsPanel) is identical regardless of which dashboard you're on --
  // so it doesn't matter *which* of a project's dashboards this links to
  // when it has more than one.
  const dashboardLinkByProject = useMemo(() => {
    const map = new Map<string, string>();
    for (const dashboard of dashboards) {
      if (!map.has(dashboard.project_id)) map.set(dashboard.project_id, dashboard.id);
    }
    return map;
  }, [dashboards]);

  function projectName(projectId: string): string {
    return projects.find((project) => project.id === projectId)?.name ?? "—";
  }

  function projectLink(projectId: string): string {
    const dashboardId = dashboardLinkByProject.get(projectId);
    return dashboardId ? `/dashboards/${dashboardId}` : "/dashboards/new";
  }

  const countsByProject = useMemo(() => {
    const map = new Map<string, EventRuleCount[]>();
    for (const count of counts) {
      const existing = map.get(count.project_id) ?? [];
      existing.push(count);
      map.set(count.project_id, existing);
    }
    return map;
  }, [counts]);

  return (
    <main className="page">
      <h1>IoTOps</h1>
      <p style={{ marginTop: 8, marginBottom: 24, maxWidth: 640 }}>
        Self-hosted IoT operations platform. Configure telemetry collectors, automation rules, and
        dashboards without hand-writing config files.
      </p>

      <div className="status-card">
        <span>Backend</span>
        <span className={`status-dot status-dot--${backendStatus}`} />
        <span>{backendStatus}</span>
      </div>

      <section className="home-events">
        <h2 style={{ marginTop: 32, marginBottom: 12 }}>Events</h2>
        {loading ? (
          <p className="home-events__hint">Loading...</p>
        ) : countsByProject.size === 0 ? (
          <p className="home-events__hint">
            No events yet. They'll show up here once a Rule fires — see{" "}
            <Link to="/automaters">Automater</Link>.
          </p>
        ) : (
          <div className="home-events__projects">
            {[...countsByProject.entries()].map(([projectId, projectCounts]) => (
              <div key={projectId} className="home-events__project-card">
                <div className="home-events__project-header">
                  <Link to={projectLink(projectId)}>{projectName(projectId)}</Link>
                </div>
                <ul className="home-events__rule-counts">
                  {projectCounts.map((count) => (
                    <li key={count.rule_id}>
                      <span className="home-events__rule-name">{count.rule_name}</span>
                      <span className="home-events__rule-count">{count.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {latestEvents.length > 0 && (
          <>
            <h3 style={{ marginTop: 24, marginBottom: 8 }}>Latest events</h3>
            <ul className="home-events__latest">
              {latestEvents.map((event) => (
                <li key={`${event.id}-${event.flag}`}>
                  <Link to={projectLink(event.project_id)}>
                    <span className={`home-events__flag home-events__flag--${event.flag}`}>
                      {event.flag === "match" ? "Firing" : "Resolved"}
                    </span>{" "}
                    <span className="home-events__rule-name">{event.rule_name}</span>
                    <span className="home-events__latest-project"> · {projectName(event.project_id)}</span>
                    <span className="home-events__event-time"> · {relativeTime(event.matched_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <p style={{ marginTop: 24 }}>
        <Link className="button" to="/collectors">
          Go to Collectors
        </Link>
      </p>
    </main>
  );
}
