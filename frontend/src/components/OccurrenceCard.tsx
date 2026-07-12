import { useState } from "react";
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
  const identifierEntries = Object.entries(occurrence.identifiers);

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
        <div className="occurrence-card__identifiers">
          {identifierEntries.map(([key, value]) => (
            <span key={key} className="occurrence-card__identifier">
              {key}: {value}
            </span>
          ))}
        </div>
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
