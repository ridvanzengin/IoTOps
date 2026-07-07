import { apiRequest } from "./client";

export function generateSql(
  prompt: string,
  variables: { name: string; label: string }[] = [],
): Promise<{ sql: string }> {
  return apiRequest<{ sql: string }>("/api/ai/sql", {
    method: "POST",
    body: JSON.stringify({ prompt, variables }),
  });
}
