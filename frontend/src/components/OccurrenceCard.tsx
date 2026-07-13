import { useState } from "react";
import { useEvents } from "../context/EventsContext";
import type { Occurrence } from "../types/event";
import "./OccurrenceCard.css";

function relativeTime(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// Attribution/plumbing tags -- already surfaced elsewhere (panel header,
// status badge) or not user-meaningful -- dropped from the drawer's raw
// dump so it reads as "what the rule saw" rather than internal wiring.
const HIDDEN_DETAIL_KEYS = new Set(["automater_id", "flag", "matched_rule_id", "project_id"]);

function detailPayload(occurrence: Occurrence): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...occurrence.tags, ...occurrence.fields };
  for (const key of HIDDEN_DETAIL_KEYS) delete merged[key];
  return merged;
}

export function OccurrenceCard({ occurrence }: { occurrence: Occurrence }) {
  const [expanded, setExpanded] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);
  const { activeDashboardVariables, openDashboardAndSelectIdentifiers } = useEvents();
  const identifierEntries = Object.entries(occurrence.identifiers);

  // Clicking *any* identifier chip applies the occurrence's whole
  // identifiers dict, not just that one key/value -- an occurrence's
  // identifiers are naturally a set (e.g. apiary_id + hive_id together),
  // and applying them one at a time was exactly what made a same-click
  // set a variable to a value that looked invalid: hive-4 only fails
  // against Hive's *current* options if Apiary hasn't been updated to
  // apiary-2 yet. Applying the full set together, in dependency order,
  // is what selectIdentifiers (registered by whichever dashboard is
  // open) actually does -- see EventsContext.tsx's comment on it.
  //
  // An identifier key only lines up with a dashboard variable if that
  // variable's value_column happens to be named identically, and
  // there's no enforced relationship between the two (see
  // iotops-workspace/ROADMAP.md's AI Co-pilot design notes) -- so a miss
  // here is a normal outcome, not an error condition worth alarming
  // over.
  function handleIdentifierClick() {
    if (activeDashboardVariables && activeDashboardVariables.projectId === occurrence.project_id) {
      const hasMatch = activeDashboardVariables.variables.some(
        (variable) => occurrence.identifiers[variable.value_column] !== undefined,
      );
      if (!hasMatch) {
        setMatchError("No open dashboard variable matches this event's identifiers.");
        return;
      }
      setMatchError(null);
      activeDashboardVariables.selectIdentifiers(occurrence.identifiers);
      return;
    }

    // No dashboard open, or a different project's -- open this
    // occurrence's own project's default dashboard and apply the
    // selection once it loads.
    const result = openDashboardAndSelectIdentifiers(occurrence.project_id, occurrence.identifiers);
    setMatchError(result.ok ? null : result.message);
  }

  return (
    <li className={`occurrence-card occurrence-card--${occurrence.severity}`}>
      <div className="occurrence-card__header">
        <span className={`occurrence-card__status occurrence-card__status--${occurrence.status}`}>
          {occurrence.status === "active" ? "Active" : "Resolved"}
        </span>
        <span className="occurrence-card__time">{relativeTime(occurrence.matched_at)}</span>
      </div>
      <div className="occurrence-card__rule">{occurrence.rule_name}</div>
      {identifierEntries.length > 0 && (
        <>
          <div className="occurrence-card__identifiers">
            {identifierEntries.map(([key, value]) => (
              <button
                key={key}
                type="button"
                className="occurrence-card__identifier"
                onClick={handleIdentifierClick}
                title="Set matching dashboard variable(s) to this occurrence's identifiers"
              >
                {key}: {value}
              </button>
            ))}
          </div>
          {matchError && <p className="occurrence-card__identifier-error">{matchError}</p>}
        </>
      )}

      <div className="occurrence-card__expand-row">
        <button
          type="button"
          className="occurrence-card__expand"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Hide detail" : "Show detail"}
        </button>
      </div>
      {expanded && (
        <div className="occurrence-card__drawer">
          <dl className="occurrence-card__drawer-list">
            <dt>Matched</dt>
            <dd>{new Date(occurrence.matched_at).toLocaleString()}</dd>
            <dt>Resolved</dt>
            <dd>{occurrence.resolved_at ? new Date(occurrence.resolved_at).toLocaleString() : "—"}</dd>
            <dt>Severity</dt>
            <dd>{occurrence.severity}</dd>
            {occurrence.category && (
              <>
                <dt>Category</dt>
                <dd>{occurrence.category}</dd>
              </>
            )}
            {occurrence.event_type && (
              <>
                <dt>Event type</dt>
                <dd>{occurrence.event_type}</dd>
              </>
            )}
            {occurrence.message && (
              <>
                <dt>Message</dt>
                <dd>{occurrence.message}</dd>
              </>
            )}
          </dl>
          <pre className="occurrence-card__drawer-json">{JSON.stringify(detailPayload(occurrence), null, 2)}</pre>
        </div>
      )}
    </li>
  );
}
