import { apiRequest } from "./client";
import type { Project, ProjectInputPayload } from "../types/project";

export function listProjects(): Promise<Project[]> {
  return apiRequest<Project[]>("/api/project");
}

export function getProject(id: string): Promise<Project> {
  return apiRequest<Project>(`/api/project/${id}`);
}

export function createProject(payload: ProjectInputPayload): Promise<Project> {
  return apiRequest<Project>("/api/project", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateProject(id: string, payload: ProjectInputPayload): Promise<Project> {
  return apiRequest<Project>(`/api/project/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteProject(id: string): Promise<void> {
  return apiRequest<void>(`/api/project/${id}`, { method: "DELETE" });
}
