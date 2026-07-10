import { apiRequest } from "./client";
import type { Automater, AutomaterInputPayload, CreateRuleRequest } from "../types/automater";

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

export function createRule(payload: CreateRuleRequest): Promise<Automater> {
  return apiRequest<Automater>("/api/automater/rules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function setRuleEnabled(
  automaterId: string,
  ruleId: string,
  enabled: boolean,
): Promise<Automater> {
  return apiRequest<Automater>(`/api/automater/${automaterId}/rules/${ruleId}/enabled`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
}

export function deleteRule(automaterId: string, ruleId: string): Promise<Automater> {
  return apiRequest<Automater>(`/api/automater/${automaterId}/rules/${ruleId}`, {
    method: "DELETE",
  });
}
