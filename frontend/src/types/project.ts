export interface Project {
  schema_version: number;
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectInputPayload {
  name: string;
  description: string;
}
