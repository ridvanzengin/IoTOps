import { apiRequest } from "./client";
import type { Plugin, PluginCategory } from "../types/plugin";

export function listPlugins(category?: PluginCategory): Promise<Plugin[]> {
  const query = category ? `?category=${category}` : "";
  return apiRequest<Plugin[]>(`/api/plugin${query}`);
}
