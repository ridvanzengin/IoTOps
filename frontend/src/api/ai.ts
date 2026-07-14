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

// No `variables` -- Dashboard Variables don't exist in a Query Rule's
// context (no dashboard, no time range control). `identifiers` is
// whatever the author's already typed into the Identifiers field, if
// anything -- a hint for both table selection and GROUP BY.
export function generateQueryRuleSql(prompt: string, identifiers: string[] = []): Promise<{ sql: string }> {
  return apiRequest<{ sql: string }>("/api/ai/query-rule-sql", {
    method: "POST",
    body: JSON.stringify({ prompt, identifiers }),
  });
}
