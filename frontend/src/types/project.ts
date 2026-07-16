export interface Project {
  schema_version: number;
  id: string;
  name: string;
  description: string;
  ai_context: string;
  default_dashboard_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectInputPayload {
  name: string;
  description: string;
  ai_context: string;
  default_dashboard_id: string | null;
}
