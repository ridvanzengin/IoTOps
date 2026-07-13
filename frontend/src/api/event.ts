import { apiRequest } from "./client";
import type { Event, EventRuleCount, Occurrence, ProjectUnresolvedCount } from "../types/event";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function listEvents(projectId?: string, limit = 50): Promise<Event[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (projectId) params.set("project_id", projectId);
  return apiRequest<Event[]>(`/api/event?${params}`);
}

// For the Panel-overlay feature: a specific set of Rules' events within a
// specific time window (the panel's own resolved [time_from, time_to]),
// not project-scoped -- see iotops-workspace/ROADMAP.md's "Events-as-
// overlay on Panel charts" note.
export function listEventsForOverlay(ruleIds: string[], since: string, until: string): Promise<Event[]> {
  // 200 is GET /api/event's own hard cap (le=200) -- also plenty for a
  // chart overlay in practice, since more than ~200 markers in one
  // window would be unreadable as vertical lines anyway.
  const params = new URLSearchParams({ since, until, limit: "200" });
  for (const ruleId of ruleIds) params.append("rule_id", ruleId);
  return apiRequest<Event[]>(`/api/event?${params}`);
}

export function getEventCounts(projectId?: string): Promise<EventRuleCount[]> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  return apiRequest<EventRuleCount[]>(`/api/event/counts?${params}`);
}

export function listOccurrences(projectId?: string, limit = 50): Promise<Occurrence[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (projectId) params.set("project_id", projectId);
  return apiRequest<Occurrence[]>(`/api/event/occurrences?${params}`);
}

export function getUnresolvedCounts(): Promise<ProjectUnresolvedCount[]> {
  return apiRequest<ProjectUnresolvedCount[]>("/api/event/unresolved-counts");
}

// occurrenceId is Occurrence.id (the underlying match Event's own id) --
// only valid for a still-active occurrence from a manual-resolve Rule. The
// backend writes a synthetic clear Event and publishes it over the same
// SSE stream subscribeToEvents listens to, so the caller doesn't need to
// locally patch `occurrences` state itself -- EventsContext's existing
// reconciliation picks it up live.
export function resolveOccurrence(occurrenceId: string, notes: string): Promise<Occurrence> {
  return apiRequest<Occurrence>(`/api/event/occurrences/${occurrenceId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ notes }),
  });
}

// EventSource (not apiRequest/fetch) -- the browser's native SSE client,
// which owns its own reconnect-on-drop behavior. Returns the EventSource
// itself so the caller controls its lifecycle. One connection for the
// whole session (opened once by EventsProvider) -- not project-scoped,
// unlike the other endpoints here; the caller filters by project_id
// client-side.
export function subscribeToEvents(onEvent: (event: Event) => void): EventSource {
  const source = new EventSource(`${API_BASE}/api/event/stream`);
  source.addEventListener("event", (message) => {
    onEvent(JSON.parse((message as MessageEvent).data) as Event);
  });
  return source;
}
