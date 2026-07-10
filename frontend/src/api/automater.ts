import { apiRequest } from "./client";
import type { Automater, AutomaterInputPayload } from "../types/automater";

export function listAutomaters(): Promise<Automater[]> {
  return apiRequest<Automater[]>("/api/automater");
}

export function getAutomater(id: string): Promise<Automater> {
  return apiRequest<Automater>(`/api/automater/${id}`);
}

export function createAutomater(payload: AutomaterInputPayload): Promise<Automater> {
  return apiRequest<Automater>("/api/automater", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAutomater(id: string, payload: AutomaterInputPayload): Promise<Automater> {
  return apiRequest<Automater>(`/api/automater/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteAutomater(id: string): Promise<void> {
  return apiRequest<void>(`/api/automater/${id}`, { method: "DELETE" });
}

export function deployAutomater(id: string): Promise<Automater> {
  return apiRequest<Automater>(`/api/automater/${id}/deployment`, { method: "POST" });
}

export function stopAutomaterDeployment(id: string): Promise<Automater> {
  return apiRequest<Automater>(`/api/automater/${id}/deployment`, { method: "DELETE" });
}
