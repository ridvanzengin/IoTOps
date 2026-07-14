import { apiRequest } from "./client";
import type {
  Event,
  EventRuleCount,
  Occurrence,
  OccurrencePage,
  OccurrenceStatus,
  ProjectUnresolvedCount,
} from "../types/event";

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

// Counts paired Occurrences, not raw match-flag Events -- unlike
// getEventCounts (a lifetime "how many times has this fired" stat, used
// on Home), this is what EventsPanel's rule filter chips need: a chip's
// count has to equal how many cards clicking it actually reveals. `range`
// is a relative code (see constants/timeRanges.ts), resolved server-side
// against the server's own clock -- same convention as the Dashboard's
// own time-range selector.
export function getOccurrenceCounts(projectId: string, range: string, search?: string): Promise<EventRuleCount[]> {
  const params = new URLSearchParams({ project_id: projectId, range });
  if (search) params.set("search", search);
  return apiRequest<EventRuleCount[]>(`/api/event/occurrence-counts?${params}`);
}

export interface ListOccurrencesOptions {
  limit?: number;
  offset?: number;
  ruleIds?: string[];
  status?: OccurrenceStatus;
  range?: string;
  search?: string;
}

// `ruleIds`/`status`/`range`/`search` all scope the query on the backend
// itself (not a client-side filter of an unrelated generic fetch) -- pass
// them whenever the caller wants "all occurrences matching X", so the
// returned `total` is the actual answer to that question instead of
// whatever a fixed-size, unscoped window happened to contain. See
// EventsContext's occurrenceFilter/timeRange/search handling, which is
// what this was added for.
export function listOccurrences(projectId?: string, options: ListOccurrencesOptions = {}): Promise<OccurrencePage> {
  const { limit = 20, offset = 0, ruleIds, status, range = "1h", search } = options;
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), range });
  if (projectId) params.set("project_id", projectId);
  if (status) params.set("status", status);
  if (search) params.set("search", search);
  if (ruleIds) for (const ruleId of ruleIds) params.append("rule_id", ruleId);
  return apiRequest<OccurrencePage>(`/api/event/occurrences?${params}`);
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
