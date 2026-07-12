import { useEffect, useMemo, useRef, useState } from "react";
import { getEventCounts } from "../api/event";
import { useEvents } from "../context/EventsContext";
import { OccurrenceCard } from "./OccurrenceCard";
import type { EventRuleCount } from "../types/event";
import "./EventsPanel.css";

type Filter = { kind: "rule"; ruleId: string } | { kind: "unresolved" } | null;

const WIDTH_STORAGE_KEY = "iotops:events-panel-width";
const DEFAULT_WIDTH = 340;
const MIN_WIDTH = 280;
const MAX_WIDTH = 640;

function loadStoredWidth(): number {
  const raw = typeof window !== "undefined" ? window.localStorage.getItem(WIDTH_STORAGE_KEY) : null;
  const parsed = raw ? Number(raw) : NaN;
  return Number.isFinite(parsed) ? Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, parsed)) : DEFAULT_WIDTH;
}

// Rendered by the app shell when the ActivityBar's project or Co-pilot
// icon is clicked -- replaces the old DashboardSidebar, which was
// embedded per-Dashboard and owned its own per-mount fetch/SSE effect.
// This reads everything from EventsContext instead, so it's reachable
// from any page and doesn't tear down/reopen the underlying connection
// as panels open and close. See iotops-workspace/ROADMAP.md's "Events
// sidebar polish" note.
export function EventsPanel() {
  const { activePanel, occurrences, occurrencesLoading, projects, unresolvedCounts, closePanel } = useEvents();
  const [ruleCounts, setRuleCounts] = useState<EventRuleCount[]>([]);
  const [filter, setFilter] = useState<Filter>(null);
  // Local state, not context: this component is mounted once at the app
  // shell root (see App.tsx) and never unmounts on route changes, so a
  // plain useState already "remembers" the width across page navigation
  // for free -- persisting to localStorage on top of that is what makes
  // it survive a full reload/new session too.
  const [width, setWidth] = useState(loadStoredWidth);
  const resizingRef = useRef(false);

  const projectId = activePanel?.kind === "project" ? activePanel.projectId : null;

  useEffect(() => {
    setFilter(null);
    if (!projectId) {
      setRuleCounts([]);
      return;
    }
    let cancelled = false;
    getEventCounts(projectId)
      .then((counts) => !cancelled && setRuleCounts(counts))
      .catch(() => !cancelled && setRuleCounts([]));
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    // The panel sits at the far right of the shell (see App.tsx), so its
    // resize handle is on its *left* edge -- width tracks the distance
    // from the viewport's right edge to the cursor, not raw clientX.
    function handleMouseMove(event: MouseEvent) {
      if (!resizingRef.current) return;
      const next = window.innerWidth - event.clientX;
      setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next)));
    }
    function handleMouseUp() {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  useEffect(() => {
    window.localStorage.setItem(WIDTH_STORAGE_KEY, String(width));
  }, [width]);

  function handleResizeStart() {
    resizingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  const visibleOccurrences = useMemo(() => {
    if (!filter) return occurrences;
    if (filter.kind === "unresolved") return occurrences.filter((o) => o.status === "active");
    return occurrences.filter((o) => o.rule_id === filter.ruleId);
  }, [occurrences, filter]);

  function toggleRuleFilter(ruleId: string) {
    setFilter((prev) => (prev?.kind === "rule" && prev.ruleId === ruleId ? null : { kind: "rule", ruleId }));
  }

  function toggleUnresolvedFilter() {
    setFilter((prev) => (prev?.kind === "unresolved" ? null : { kind: "unresolved" }));
  }

  if (!activePanel) return null;

  const project = projects.find((p) => p.id === projectId);
  const unresolvedCount = projectId ? (unresolvedCounts[projectId] ?? 0) : 0;
  const title = activePanel.kind === "copilot" ? "Co-pilot" : (project?.name ?? "Events");

  return (
    <aside className="events-panel" style={{ width }}>
      <div className="events-panel__resize-handle" onMouseDown={handleResizeStart} />
      <div className="events-panel__header">
        <span className="events-panel__title">{title}</span>
        <button type="button" className="events-panel__close" onClick={closePanel} aria-label="Close panel">
          ×
        </button>
      </div>
      {activePanel.kind === "copilot" ? (
        <div className="events-panel__body events-panel__body--placeholder">
          <p className="events-panel__hint">Co-pilot is coming soon.</p>
        </div>
      ) : (
        <div className="events-panel__body">
          {occurrencesLoading ? (
            <p className="events-panel__hint">Loading...</p>
          ) : occurrences.length === 0 ? (
            <p className="events-panel__hint">
              No events yet. They'll show up here as soon as a Rule in this project fires.
            </p>
          ) : (
            <>
              <div className="events-panel__filters">
                {unresolvedCount > 0 && (
                  <button
                    type="button"
                    className={`events-panel__filter-badge events-panel__filter-badge--unresolved ${
                      filter?.kind === "unresolved" ? "events-panel__filter-badge--active" : ""
                    }`}
                    onClick={toggleUnresolvedFilter}
                  >
                    Active
                    <span className="events-panel__filter-count">{unresolvedCount}</span>
                  </button>
                )}
                {ruleCounts.map((rc) => (
                  <button
                    key={rc.rule_id}
                    type="button"
                    className={`events-panel__filter-badge ${
                      filter?.kind === "rule" && filter.ruleId === rc.rule_id
                        ? "events-panel__filter-badge--active"
                        : ""
                    }`}
                    title={rc.rule_name}
                    onClick={() => toggleRuleFilter(rc.rule_id)}
                  >
                    <span className="events-panel__filter-badge-label">{rc.rule_name}</span>
                    <span className="events-panel__filter-count">{rc.count}</span>
                  </button>
                ))}
              </div>
              {visibleOccurrences.length === 0 ? (
                <p className="events-panel__hint">No events match this filter.</p>
              ) : (
                <ul className="events-panel__list">
                  {visibleOccurrences.map((occurrence) => (
                    <OccurrenceCard
                      key={`${occurrence.rule_id}-${occurrence.matched_at}-${JSON.stringify(occurrence.identifiers)}`}
                      occurrence={occurrence}
                    />
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </aside>
  );
}
