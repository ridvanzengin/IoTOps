export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

export interface NeedsContext {
  column: string;
  reason: string;
}
