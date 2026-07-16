import { useEffect, useRef, useState } from "react";
import { OCCURRENCES_PAGE_SIZE, useEvents } from "../context/EventsContext";
import { TIME_RANGES } from "../constants/timeRanges";
import { hashColor } from "../utils/color";
import { CopilotChat } from "./CopilotChat";
import { OccurrenceCard } from "./OccurrenceCard";
import "./EventsPanel.css";

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
  const {
    activePanel,
    occurrences,
    occurrencesLoading,
    occurrencesTotal,
    occurrencesOffset,
    occurrenceFilter,
    timeRange,
    searchQuery,
    ruleCounts,
    activeCount,
    projects,
    closePanel,
    setOccurrenceFilter,
    setTimeRange,
    setSearchQuery,
    loadOccurrencesPage,
  } = useEvents();
  // Local state, not context: this component is mounted once at the app
  // shell root (see App.tsx) and never unmounts on route changes, so a
  // plain useState already "remembers" the width across page navigation
  // for free -- persisting to localStorage on top of that is what makes
  // it survive a full reload/new session too.
  const [width, setWidth] = useState(loadStoredWidth);
  const resizingRef = useRef(false);

  const projectId = activePanel?.kind === "project" ? activePanel.projectId : null;

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

  function toggleRuleFilter(ruleId: string) {
    setOccurrenceFilter(
      occurrenceFilter?.kind === "rule" && occurrenceFilter.ruleId === ruleId ? null : { kind: "rule", ruleId },
    );
  }

  function toggleUnresolvedFilter() {
    setOccurrenceFilter(occurrenceFilter?.kind === "unresolved" ? null : { kind: "unresolved" });
  }

  if (!activePanel) return null;

  const project = projects.find((p) => p.id === projectId);
  const title = activePanel.kind === "copilot" ? "Co-pilot" : (project?.name ?? "Events");
  const hasAnyFilterChips = ruleCounts.length > 0 || activeCount > 0;
  const pageStart = occurrencesTotal === 0 ? 0 : occurrencesOffset + 1;
  const pageEnd = Math.min(occurrencesOffset + OCCURRENCES_PAGE_SIZE, occurrencesTotal);

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
        <div className="events-panel__body">
          <CopilotChat />
        </div>
      ) : (
        <div className="events-panel__body">
          <div className="events-panel__toolbar">
            <select
              className="events-panel__range"
              value={timeRange}
              onChange={(event) => setTimeRange(event.target.value)}
              aria-label="Time range"
              disabled={occurrenceFilter?.kind === "unresolved"}
              title={
                occurrenceFilter?.kind === "unresolved"
                  ? "Active occurrences aren't limited by time range"
                  : undefined
              }
            >
              {TIME_RANGES.map((range) => (
                <option key={range.code} value={range.code}>
                  {range.label}
                </option>
              ))}
            </select>
            <input
              type="text"
              className="events-panel__search"
              placeholder="Search events..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              aria-label="Search events"
            />
          </div>

          {hasAnyFilterChips && (
            <div className="events-panel__filters">
              {activeCount > 0 && (
                <button
                  type="button"
                  className={`events-panel__filter-badge events-panel__filter-badge--unresolved ${
                    occurrenceFilter?.kind === "unresolved" ? "events-panel__filter-badge--active" : ""
                  }`}
                  onClick={toggleUnresolvedFilter}
                >
                  Active
                  <span className="events-panel__filter-count">{activeCount}</span>
                </button>
              )}
              {ruleCounts.map((rc) => (
                <button
                  key={rc.rule_id}
                  type="button"
                  className={`events-panel__filter-badge events-panel__filter-badge--rule ${
                    occurrenceFilter?.kind === "rule" && occurrenceFilter.ruleId === rc.rule_id
                      ? "events-panel__filter-badge--active"
                      : ""
                  }`}
                  style={{ "--rule-color": hashColor(rc.rule_id) } as React.CSSProperties}
                  title={rc.rule_name}
                  onClick={() => toggleRuleFilter(rc.rule_id)}
                >
                  <span className="events-panel__filter-badge-label">{rc.rule_name}</span>
                  <span className="events-panel__filter-count">{rc.count}</span>
                </button>
              ))}
            </div>
          )}

          {occurrencesLoading ? (
            <p className="events-panel__hint">Loading...</p>
          ) : occurrences.length === 0 ? (
            <p className="events-panel__hint">
              No events match the current time range/filters. Try widening the time range above.
            </p>
          ) : (
            <>
              <ul className="events-panel__list">
                {occurrences.map((occurrence) => (
                  <OccurrenceCard
                    key={`${occurrence.rule_id}-${occurrence.matched_at}-${JSON.stringify(occurrence.identifiers)}`}
                    occurrence={occurrence}
                  />
                ))}
              </ul>
              {occurrencesTotal > OCCURRENCES_PAGE_SIZE && (
                <div className="events-panel__pagination">
                  <button
                    type="button"
                    className="events-panel__page-button"
                    disabled={occurrencesOffset === 0}
                    onClick={() => loadOccurrencesPage(Math.max(0, occurrencesOffset - OCCURRENCES_PAGE_SIZE))}
                  >
                    Prev
                  </button>
                  <span className="events-panel__page-status">
                    {pageStart}–{pageEnd} of {occurrencesTotal}
                  </span>
                  <button
                    type="button"
                    className="events-panel__page-button"
                    disabled={pageEnd >= occurrencesTotal}
                    onClick={() => loadOccurrencesPage(occurrencesOffset + OCCURRENCES_PAGE_SIZE)}
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </aside>
  );
}
