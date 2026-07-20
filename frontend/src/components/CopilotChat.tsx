import { Fragment, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { askCopilot } from "../api/ai";
import { ApiError } from "../api/client";
import { useEvents } from "../context/EventsContext";
import type { Project } from "../types/project";
import type { CopilotIntent, CopilotSuggestion } from "../types/ai";
import "./CopilotChat.css";

const ASSISTANT_NAME = "ARIA";
const TYPE_SPEED_MS = 16;

// A single tap to kick off the suggest-automation flow without typing --
// the button's own label doubles as the message it sends, so there's one
// string to keep in sync, not a short label plus a separate long message.
const SUGGEST_AUTOMATION_SEED_REPLY = "Analyze my telemetry and suggest an automation";
const SUGGEST_PANEL_SEED_REPLY = "Suggest a panel for this dashboard";

// Shown instead of the two single-purpose seed chips above when the
// conversation was opened generically (no intent, no known dashboard) --
// three short-labeled entry points into the same underlying flows, rather
// than making the user type out a request from scratch. Labels are short
// (fit three side by side); the actual sent message can be a little more
// explicit than the label since only the model sees it.
const GENERIC_ANALYZE_SEED_REPLY = "Analyze my current telemetry and tell me what's notable";
const GENERIC_SUGGEST_PANEL_SEED_REPLY = "Suggest a dashboard panel worth adding";

// Only ever rendered when the project-chip picker is actually about to be
// shown (see the `skippedPicker` guard around this component's render) --
// when the project is already known upfront, this question is never put to
// the user at all, so it doesn't need a "skip the question" variant here.
function greetingText(intent?: CopilotIntent): string {
  if (intent === "suggest-automation") {
    return `Hi, I'm ${ASSISTANT_NAME}. Which project would you like to set up an automation for?`;
  }
  if (intent === "suggest-panel") {
    return `Hi, I'm ${ASSISTANT_NAME}. Which project would you like to suggest a panel for?`;
  }
  return `Hi, I'm ${ASSISTANT_NAME} — your IoTOps assistant. Which project do you need help with today?`;
}

// Matches the block AiService appends to an answer whenever it produced a
// suggestion this turn (see backend app/ai/service.py's
// _SUGGESTION_CONTEXT_START/_END) -- kept in the stored message content so
// it round-trips as history for a later refinement turn, but stripped here
// before display so the user never sees the raw JSON recap. Global: a
// refinement turn's own model response has been observed echoing this same
// bracket pattern itself (mimicking what it saw in its own prior turn's
// history), producing more than one block in a single answer -- every
// occurrence must go, not just the first.
const SUGGESTION_CONTEXT_RE = /\n\n\[\[suggestion-context\]\][\s\S]*?\[\[\/suggestion-context\]\]/g;

// The backend already strips every `[[quick-replies]]...[[/quick-replies]]`
// block out of `answer` before returning it (see AiService's
// _extract_quick_replies) -- unlike suggestion-context, these never round-
// trip as stored message content. This is a defensive backstop only, in
// case a malformed/partial block ever slips past that server-side strip.
const QUICK_REPLIES_RE = /\n*\[\[quick-replies\]\][\s\S]*?\[\[\/quick-replies\]\]/g;

// The system prompt allows the model **bold** for emphasis and numbered
// lists for enumerating options (see build_copilot_system_prompt) -- it
// reliably uses both, so rather than fight that, render bold inline.
// Numbered/bulleted lines need no special handling: `.copilot-chat__message`
// already sets white-space: pre-wrap, so each line the model puts on its
// own line already wraps as a separate visual line.
const BOLD_RE = /\*\*(.+?)\*\*/g;

function renderAssistantContent(content: string): ReactNode {
  const stripped = content.replace(SUGGESTION_CONTEXT_RE, "").replace(QUICK_REPLIES_RE, "");
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  BOLD_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = BOLD_RE.exec(stripped)) !== null) {
    if (match.index > lastIndex) parts.push(stripped.slice(lastIndex, match.index));
    parts.push(<strong key={match.index}>{match[1]}</strong>);
    lastIndex = BOLD_RE.lastIndex;
  }
  if (lastIndex < stripped.length) parts.push(stripped.slice(lastIndex));
  return parts;
}

function ackText(project: Project, intent?: CopilotIntent): string {
  if (intent === "suggest-automation") {
    return `Let's set up an automation for ${project.name}. What would you like to detect?`;
  }
  if (intent === "suggest-panel") {
    return `Let's find a chart worth adding to your dashboard. What would you like to see?`;
  }
  return `How can I help you with ${project.name}?`;
}

// Only covers the two suggestion kinds with a static route -- "panel"
// needs a runtime dashboard id and is handled directly in
// handleOpenSuggestion instead (see there).
function suggestionRoute(kind: "automater_rule" | "query_rule"): string {
  return kind === "automater_rule" ? "/automaters/new" : "/query-rules/new";
}

// Reveals `text` one character at a time, like the assistant is typing it
// live -- purely a UI effect, not an actual streamed response (the backend
// returns the full answer in one shot; only these two scripted lines are
// "typed"). Remounts (via a `key` prop) restart the reveal from scratch.
function TypedLine({ text, onDone }: { text: string; onDone?: () => void }) {
  const [shown, setShown] = useState("");

  useEffect(() => {
    let index = 0;
    const id = window.setInterval(() => {
      index += 1;
      setShown(text.slice(0, index));
      if (index >= text.length) {
        window.clearInterval(id);
        onDone?.();
      }
    }, TYPE_SPEED_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const done = shown.length >= text.length;
  return (
    <>
      {shown}
      {!done && <span className="copilot-chat__typing-cursor" />}
    </>
  );
}

// Self-contained-looking, but the actual conversation state lives in
// EventsContext's copilotSession (see there), not local useState -- this
// component mounts/unmounts every time the events sidebar is shown instead
// (EventsPanel's activePanel ternary) or the panel is closed (EventsPanel
// returns null when activePanel is null), and a mount-local conversation
// would silently vanish on either. Rehydrating from context on every mount
// means those toggles are invisible to the user; only an explicit "New
// session" (resetCopilotSession) or a hard page reload actually clears it.
// The multi-tool-call loop happens entirely server-side; this component
// only ever sees the flat {role, content} transcript for the real
// conversation -- the greeting/project-pick/acknowledgement above it is a
// scripted, client-only sequence, never sent to the backend as history.
export function CopilotChat({
  intent,
  dashboardId,
  projectId,
}: {
  intent?: CopilotIntent;
  dashboardId?: string;
  projectId?: string;
}) {
  const { projects, copilotSession, updateCopilotSession } = useEvents();
  const navigate = useNavigate();
  const listRef = useRef<HTMLDivElement>(null);

  const {
    project,
    messages,
    needsContextByIndex,
    suggestionByIndex,
    quickRepliesByIndex,
    greetingDone,
    ackDone,
    input,
    sending,
    error,
  } = copilotSession;

  // Frozen at the moment `project` is first set (see handleSelectProject),
  // not tracked live from props: once a conversation has real content, the
  // panel can be reopened via a *different* entry point (e.g. the plain
  // Co-pilot icon, with no intent/dashboardId at all) without silently
  // redirecting in-flight messages to a different dashboard's context out
  // from under the still-visible transcript about the original one.
  const effectiveIntent = project ? copilotSession.intent : intent;
  const effectiveDashboardId = project ? copilotSession.dashboardId : dashboardId;
  // Pre-selection: reflects the live prop/project-count (we already know
  // the picker is about to be skipped). Post-selection: reflects the
  // frozen session field, not `project !== null` -- otherwise a session
  // that started via the *manual* chip picker would also (incorrectly)
  // suppress its own "you picked this project" echo bubble, since project
  // is truthy there too by that point.
  const skippedPicker = project
    ? Boolean(copilotSession.pickerSkipped)
    : Boolean(projectId) || projects.length === 1;

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, greetingDone, project, ackDone, sending]);

  // Skips the project-chip picker either when the caller already knows
  // which project this conversation is about (e.g. "Suggest a panel",
  // opened from inside an already-open dashboard -- see development-
  // plan.md's "shortcut" note for that entry point specifically), or when
  // there's only one project to begin with, in which case asking which
  // project to help with has exactly one possible answer and isn't a
  // real question.
  useEffect(() => {
    if (project) return;
    const target = projectId
      ? projects.find((candidate) => candidate.id === projectId)
      : projects.length === 1
        ? projects[0]
        : undefined;
    if (target) handleSelectProject(target, { pickerSkipped: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, projects]);

  function handleSelectProject(next: Project, opts?: { pickerSkipped?: boolean }) {
    // A new project is a new conversation -- avoids a transcript that
    // silently mixes which project's data grounds the answers. Also the
    // moment intent/dashboardId/pickerSkipped freeze into the session
    // (see the effectiveIntent/effectiveDashboardId/skippedPicker
    // comments above).
    updateCopilotSession({
      project: next,
      intent,
      dashboardId,
      pickerSkipped: opts?.pickerSkipped ?? false,
      ackDone: false,
      messages: [],
      needsContextByIndex: {},
      suggestionByIndex: {},
      quickRepliesByIndex: {},
      error: null,
    });
  }

  async function sendMessage(question: string) {
    if (!project || !question.trim() || sending) return;
    const nextMessages = [...messages, { role: "user" as const, content: question }];
    updateCopilotSession({ messages: nextMessages, input: "", sending: true, error: null });
    try {
      const { answer, needs_context, suggestion, quick_replies } = await askCopilot(
        project.id,
        question,
        nextMessages.slice(-8),
        effectiveDashboardId,
      );
      const answerIndex = nextMessages.length;
      // `answer` may carry a trailing machine-readable recap (stripped only
      // at render time, see renderAssistantContent) -- stored as-is here
      // since this is exactly what round-trips as history on the next turn.
      updateCopilotSession((prev) => ({
        messages: [...prev.messages, { role: "assistant", content: answer }],
        ...(needs_context ? { needsContextByIndex: { ...prev.needsContextByIndex, [answerIndex]: needs_context } } : {}),
        ...(suggestion ? { suggestionByIndex: { ...prev.suggestionByIndex, [answerIndex]: suggestion } } : {}),
        ...(quick_replies ? { quickRepliesByIndex: { ...prev.quickRepliesByIndex, [answerIndex]: quick_replies } } : {}),
      }));
    } catch (err) {
      updateCopilotSession({ error: err instanceof ApiError ? err.message : "Failed to get an answer." });
    } finally {
      updateCopilotSession({ sending: false });
    }
  }

  function handleSend() {
    sendMessage(input.trim());
  }

  function handleAddContext() {
    if (!project) return;
    navigate(`/projects/${project.id}/edit`, { state: { focusField: "ai_context" } });
  }

  function handleOpenSuggestion(suggestion: CopilotSuggestion) {
    if (suggestion.kind === "panel") {
      navigate(`/dashboards/${suggestion.state.dashboard_id}/panels/new`, { state: suggestion.state });
      return;
    }
    navigate(suggestionRoute(suggestion.kind), { state: suggestion.state });
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") handleSend();
  }

  const chatting = project !== null && ackDone;

  return (
    <div className="copilot-chat">
      <div ref={listRef} className="copilot-chat__messages">
        {!skippedPicker && (
          <div className="copilot-chat__message copilot-chat__message--assistant">
            {greetingDone ? (
              greetingText(intent)
            ) : (
              <TypedLine text={greetingText(intent)} onDone={() => updateCopilotSession({ greetingDone: true })} />
            )}
          </div>
        )}

        {!skippedPicker && greetingDone && !project && (
          <div className="copilot-chat__project-chips">
            {projects.map((candidate) => (
              <button
                key={candidate.id}
                type="button"
                className="copilot-chat__project-chip"
                onClick={() => handleSelectProject(candidate)}
              >
                {candidate.name}
              </button>
            ))}
          </div>
        )}

        {project && (
          <>
            {!skippedPicker && (
              <div className="copilot-chat__message copilot-chat__message--user">{project.name}</div>
            )}
            <div className="copilot-chat__message copilot-chat__message--assistant">
              {ackDone ? (
                ackText(project, effectiveIntent)
              ) : (
                <TypedLine
                  key={project.id}
                  text={ackText(project, effectiveIntent)}
                  onDone={() => updateCopilotSession({ ackDone: true })}
                />
              )}
            </div>
            {ackDone && effectiveIntent === "suggest-automation" && messages.length === 0 && (
              <div className="copilot-chat__project-chips">
                <button
                  type="button"
                  className="copilot-chat__project-chip"
                  onClick={() => sendMessage(SUGGEST_AUTOMATION_SEED_REPLY)}
                >
                  {SUGGEST_AUTOMATION_SEED_REPLY}
                </button>
              </div>
            )}
            {ackDone && effectiveIntent === "suggest-panel" && messages.length === 0 && (
              <div className="copilot-chat__project-chips">
                <button
                  type="button"
                  className="copilot-chat__project-chip"
                  onClick={() => sendMessage(SUGGEST_PANEL_SEED_REPLY)}
                >
                  {SUGGEST_PANEL_SEED_REPLY}
                </button>
              </div>
            )}
            {ackDone && !effectiveIntent && messages.length === 0 && (
              <div className="copilot-chat__project-chips">
                <button
                  type="button"
                  className="copilot-chat__project-chip"
                  onClick={() => sendMessage(GENERIC_ANALYZE_SEED_REPLY)}
                >
                  Analyze my telemetry
                </button>
                <button
                  type="button"
                  className="copilot-chat__project-chip"
                  onClick={() => sendMessage(SUGGEST_AUTOMATION_SEED_REPLY)}
                >
                  Suggest an automation
                </button>
                <button
                  type="button"
                  className="copilot-chat__project-chip"
                  onClick={() => sendMessage(GENERIC_SUGGEST_PANEL_SEED_REPLY)}
                >
                  Suggest a dashboard panel
                </button>
              </div>
            )}
          </>
        )}

        {messages.map((message, index) => (
          <Fragment key={index}>
            <div className={`copilot-chat__message copilot-chat__message--${message.role}`}>
              {message.role === "assistant" ? renderAssistantContent(message.content) : message.content}
            </div>
            {needsContextByIndex[index] && (
              <button type="button" className="copilot-chat__context-nudge" onClick={handleAddContext}>
                I wasn't sure what <code>{needsContextByIndex[index].column}</code> means — add context →
              </button>
            )}
            {quickRepliesByIndex[index] && index === messages.length - 1 && !sending && (
              <div className="copilot-chat__project-chips">
                {quickRepliesByIndex[index].map((label) => (
                  <button
                    key={label}
                    type="button"
                    className="copilot-chat__project-chip"
                    onClick={() => sendMessage(label)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            {suggestionByIndex[index] && (
              <div className="copilot-chat__suggestion-card">
                <span className="copilot-chat__suggestion-label">{suggestionByIndex[index].label}</span>
                <button
                  type="button"
                  className="copilot-chat__suggestion-action"
                  onClick={() => handleOpenSuggestion(suggestionByIndex[index])}
                >
                  Open in builder →
                </button>
              </div>
            )}
          </Fragment>
        ))}
        {sending && <div className="copilot-chat__message copilot-chat__message--assistant">Thinking...</div>}
      </div>

      {error && <p className="collector-page__error">{error}</p>}

      <div className="copilot-chat__input-row">
        <input
          type="text"
          className="copilot-chat__input"
          placeholder={chatting ? "Ask a question..." : "Pick a project above first"}
          value={input}
          onChange={(event) => updateCopilotSession({ input: event.target.value })}
          onKeyDown={handleKeyDown}
          disabled={!chatting || sending}
        />
        <button type="button" className="button" onClick={handleSend} disabled={!chatting || !input.trim() || sending}>
          {sending ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}
