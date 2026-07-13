import type { Event, Occurrence } from "../types/event";

// Same grouping key as the backend's EventRepository._pair_occurrences:
// (rule_id, identifier values) -- must mirror it exactly, or a live SSE
// event could match the wrong rendered row (or none at all).
function identifiersFromEvent(event: Event): Record<string, string> {
  const identifiers: Record<string, string> = {};
  for (const key of event.identifier_keys) {
    identifiers[key] = event.tags[key] ?? "";
  }
  return identifiers;
}

function sameGroup(occurrence: Occurrence, event: Event): boolean {
  if (occurrence.rule_id !== event.rule_id) return false;
  const eventIdentifiers = identifiersFromEvent(event);
  const occurrenceKeys = Object.keys(occurrence.identifiers);
  const eventKeys = Object.keys(eventIdentifiers);
  if (occurrenceKeys.length !== eventKeys.length) return false;
  return occurrenceKeys.every((key) => occurrence.identifiers[key] === eventIdentifiers[key]);
}

function occurrenceFromMatch(event: Event): Occurrence {
  return {
    id: event.id,
    rule_id: event.rule_id,
    rule_name: event.rule_name,
    category: event.category,
    severity: event.severity,
    event_type: event.event_type,
    message: event.message,
    identifiers: identifiersFromEvent(event),
    status: "active",
    matched_at: event.matched_at,
    resolved_at: null,
    automater_id: event.automater_id,
    project_id: event.project_id,
    tags: event.tags,
    fields: event.fields,
    resolve_mode: event.resolve_mode,
    resolution_notes: null,
  };
}

// Applies one live-arriving raw Event to an already-rendered occurrence
// list: a clear flips its matching Active row to Resolved in place (never
// appends a new row); a match with no matching Active row prepends a new
// Active occurrence. Only one Active row can exist per (rule_id,
// identifiers) group at a time, by the pairing invariant the backend
// enforces -- see iotops-workspace/ROADMAP.md's "Events sidebar polish"
// note.
export function reconcileOccurrence(occurrences: Occurrence[], event: Event): Occurrence[] {
  const activeIndex = occurrences.findIndex((o) => o.status === "active" && sameGroup(o, event));

  if (event.flag === "clear") {
    if (activeIndex === -1) return occurrences; // stray clear, nothing open -- ignore
    const next = [...occurrences];
    next[activeIndex] = {
      ...next[activeIndex],
      status: "resolved",
      resolved_at: event.matched_at,
      resolution_notes: event.resolution_notes,
    };
    return next;
  }

  // event.flag === "match"
  if (activeIndex !== -1) return occurrences; // already open -- Go suppresses repeats, ignore defensively
  return [occurrenceFromMatch(event), ...occurrences];
}
