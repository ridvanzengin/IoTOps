import type { CopilotMessage, CopilotSuggestion, NeedsContext } from "../types/ai";
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

// The multi-tool-call loop (occurrence/telemetry lookups, rule-drafting)
// happens entirely server-side within this one request/response -- history
// is a flat transcript of prior turns' questions/answers only, never the
// internal tool_use/tool_result exchanges. No `intent` param: the backend
// always has the full tool set available (including suggest_automation/
// suggest_panel) regardless of how the panel was opened -- see
// CopilotChat.tsx's own `intent` prop, which only ever drives local
// greeting/ack/seed-chip text, never anything sent over the wire.
// `dashboardId` IS sent, though (when known) -- it lets the backend hint
// the model with that dashboard's id/name/variables so suggest_panel
// doesn't need a round-trip through list_existing_panels to discover it.
export function askCopilot(
  projectId: string,
  question: string,
  history: CopilotMessage[] = [],
  dashboardId?: string,
): Promise<{
  answer: string;
  needs_context: NeedsContext | null;
  suggestion: CopilotSuggestion | null;
  quick_replies: string[] | null;
}> {
  return apiRequest<{
    answer: string;
    needs_context: NeedsContext | null;
    suggestion: CopilotSuggestion | null;
    quick_replies: string[] | null;
  }>("/api/ai/copilot", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, question, history, dashboard_id: dashboardId }),
  });
}
