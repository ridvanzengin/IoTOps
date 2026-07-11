import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getEventCounts, listEvents, subscribeToEvents } from "../api/event";
import type { Event } from "../types/event";
import "./DashboardSidebar.css";

type Tab = "events" | "copilot";

function relativeTime(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function EventRow({ event }: { event: Event }) {
  return (
    <li className={`dashboard-sidebar__event dashboard-sidebar__event--${event.flag}`}>
      <div className="dashboard-sidebar__event-header">
        <span className={`dashboard-sidebar__flag dashboard-sidebar__flag--${event.flag}`}>
          {event.flag === "match" ? "Firing" : "Resolved"}
        </span>
        <span className="dashboard-sidebar__event-time">{relativeTime(event.matched_at)}</span>
      </div>
      <div className="dashboard-sidebar__event-rule">{event.rule_name}</div>
      {event.message && <p className="dashboard-sidebar__event-message">{event.message}</p>}
      <div className="dashboard-sidebar__event-meta">
        {event.table}
        {event.severity && ` · ${event.severity}`}
      </div>
    </li>
  );
}

// Project-scoped, not tied to an individual Dashboard: an event only ever
// relates to a Project (via Automater.project_id), never to one specific
// Dashboard, so every dashboard in a project renders this with the same
// projectId and sees identical content. See iotops-workspace/ROADMAP.md's
// "Events sidebar" note.
export function DashboardSidebar({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<Tab>("events");
  const [events, setEvents] = useState<Event[]>([]);
  const [ruleCount, setRuleCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unseenCount, setUnseenCount] = useState(0);

  // Read inside the SSE callback instead of `tab` directly -- the
  // subscription effect below only re-runs when `projectId` changes, so a
  // tab switch doesn't tear down and reopen the EventSource connection.
  const tabRef = useRef(tab);
  useEffect(() => {
    tabRef.current = tab;
    if (tab === "events") setUnseenCount(0);
  }, [tab]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([listEvents(projectId), getEventCounts(projectId)])
      .then(([fetchedEvents, counts]) => {
        if (cancelled) return;
        setEvents(fetchedEvents);
        setRuleCount(counts.length);
        setError(null);
      })
      .catch(() => !cancelled && setError("Failed to load events."))
      .finally(() => !cancelled && setLoading(false));

    const source = subscribeToEvents(projectId, (event) => {
      setEvents((prev) => [event, ...prev].slice(0, 50));
      if (tabRef.current !== "events") setUnseenCount((count) => count + 1);
    });

    return () => {
      cancelled = true;
      source.close();
    };
  }, [projectId]);

  return (
    <aside className="dashboard-sidebar">
      <div className="dashboard-sidebar__tabs">
        <button
          type="button"
          className={`dashboard-sidebar__tab ${tab === "events" ? "dashboard-sidebar__tab--active" : ""}`}
          onClick={() => setTab("events")}
        >
          Events
          {unseenCount > 0 && <span className="dashboard-sidebar__badge">{unseenCount}</span>}
        </button>
        <button
          type="button"
          className={`dashboard-sidebar__tab ${tab === "copilot" ? "dashboard-sidebar__tab--active" : ""}`}
          onClick={() => setTab("copilot")}
        >
          Co-pilot
        </button>
      </div>

      {tab === "events" ? (
        <div className="dashboard-sidebar__panel">
          {loading ? (
            <p className="dashboard-sidebar__hint">Loading...</p>
          ) : error ? (
            <p className="dashboard-sidebar__hint">{error}</p>
          ) : events.length === 0 ? (
            <p className="dashboard-sidebar__hint">
              No events yet. They'll show up here as soon as a Rule in this project fires.
            </p>
          ) : (
            <>
              {ruleCount !== null && (
                <p className="dashboard-sidebar__summary">
                  {ruleCount} rule{ruleCount === 1 ? "" : "s"} with activity ·{" "}
                  <Link to="/automaters">manage rules</Link>
                </p>
              )}
              <ul className="dashboard-sidebar__event-list">
                {events.map((event) => (
                  <EventRow key={`${event.id}-${event.flag}`} event={event} />
                ))}
              </ul>
            </>
          )}
        </div>
      ) : (
        <div className="dashboard-sidebar__panel dashboard-sidebar__panel--placeholder">
          <p className="dashboard-sidebar__hint">Co-pilot is coming soon.</p>
        </div>
      )}
    </aside>
  );
}
