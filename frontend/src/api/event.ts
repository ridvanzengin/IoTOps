import { apiRequest } from "./client";
import type { Event, EventRuleCount } from "../types/event";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function listEvents(projectId?: string, limit = 50): Promise<Event[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (projectId) params.set("project_id", projectId);
  return apiRequest<Event[]>(`/api/event?${params}`);
}

export function getEventCounts(projectId?: string): Promise<EventRuleCount[]> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  return apiRequest<EventRuleCount[]>(`/api/event/counts?${params}`);
}

// EventSource (not apiRequest/fetch) -- the browser's native SSE client,
// which owns its own reconnect-on-drop behavior. Returns the EventSource
// itself so the caller controls its lifecycle (close() on unmount).
export function subscribeToEvents(projectId: string, onEvent: (event: Event) => void): EventSource {
  const source = new EventSource(`${API_BASE}/api/event/stream?project_id=${projectId}`);
  source.addEventListener("event", (message) => {
    onEvent(JSON.parse((message as MessageEvent).data) as Event);
  });
  return source;
}
