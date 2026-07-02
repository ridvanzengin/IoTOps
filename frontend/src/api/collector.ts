import { apiRequest } from "./client";
import type { Collector, CollectorInputPayload } from "../types/collector";

export function listCollectors(): Promise<Collector[]> {
  return apiRequest<Collector[]>("/api/collector");
}

export function getCollector(id: string): Promise<Collector> {
  return apiRequest<Collector>(`/api/collector/${id}`);
}

export function createCollector(payload: CollectorInputPayload): Promise<Collector> {
  return apiRequest<Collector>("/api/collector", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCollector(id: string, payload: CollectorInputPayload): Promise<Collector> {
  return apiRequest<Collector>(`/api/collector/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteCollector(id: string): Promise<void> {
  return apiRequest<void>(`/api/collector/${id}`, { method: "DELETE" });
}

export function deployCollector(id: string): Promise<Collector> {
  return apiRequest<Collector>(`/api/collector/${id}/deployment`, { method: "POST" });
}

export function stopCollectorDeployment(id: string): Promise<Collector> {
  return apiRequest<Collector>(`/api/collector/${id}/deployment`, { method: "DELETE" });
}
