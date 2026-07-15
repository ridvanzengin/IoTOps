const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface HealthStatus {
  status: string;
  demo: boolean;
}

export async function fetchHealth(): Promise<HealthStatus> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}
