import { Fragment, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { askCopilot } from "../api/ai";
import { ApiError } from "../api/client";
import { addPanel, createDashboard } from "../api/dashboard";
import { useEvents } from "../context/EventsContext";
import { DEFAULT_POSITION, findFreePosition } from "../utils/panelLayout";
import type { Project } from "../types/project";
import type { CopilotIntent, CopilotSuggestion, DashboardSuggestionState } from "../types/ai";
import type { PanelPosition, Variable } from "../types/dashboard";
import "./CopilotChat.css";

const ASSISTANT_NAME = "ARIA";
const TYPE_SPEED_MS = 16;

// A single tap to kick off the suggest-automation flow without typing --
// the button's own label doubles as the message it sends, so there's one
// string to keep in sync, not a short label plus a separate long message.
const SUGGEST_AUTOMATION_SEED_REPLY = "Analyze my telemetry and suggest an automation";
const SUGGEST_PANEL_SEED_REPLY = "Suggest a panel for this dashboard";
const SUGGEST_DASHBOARD_SEED_REPLY = "Suggest a dashboard for this project";

// Shown instead of the single-purpose seed chips above when the
// conversation was opened generically (no intent, no known dashboard) --
// four short-labeled entry points into the same underlying flows, rather
// than making the user type out a request from scratch. Labels are short
// (fit side by side); the actual sent message can be a little more
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
    return `Hi, I'm ${ASSISTANT_NAME}. Which project should I suggest a panel for?`;
  }
  if (intent === "suggest-dashboard") {
    return `Hi, I'm ${ASSISTANT_NAME}. Which project should I suggest a dashboard for?`;
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
  if (intent === "suggest-dashboard") {
    return `Let's build a starter dashboard for ${project.name}. I'll take a look at the data and propose one.`;
  }
  return `How can I help you with ${project.name}?`;
}

// Only covers the two suggestion kinds with a static route -- "panel"
// needs a runtime dashboard id and is handled directly in
// handleOpenSuggestion instead (see there); "dashboard" has no route at
// all (see handleCreateDashboardSuggestion) and is deliberately excluded
// from handleOpenSuggestion's own parameter type so it can never reach
// this function.
function suggestionRoute(kind: "automater_rule" | "query_rule"): string {
  return kind === "automater_rule" ? "/automaters/new" : "/query-rules/new";
}

// "Apiary → Hive (filtered by Apiary)" -- readable, not raw JSON, so the
// user can actually evaluate what they're about to confirm. A variable's
// predicate_variable is a token (matches an earlier item's `name`), so
// look up that earlier item's own label for a nicer join.
function describeVariableChain(variables: Variable[]): string {
  if (variables.length === 0) return "None — flat overview, no per-entity filtering.";
  return variables
    .map((variable) => {
      if (!variable.predicate_variable) return variable.label;
      const parent = variables.find((candidate) => candidate.name === variable.predicate_variable);
      return `${variable.label} (filtered by ${parent?.label ?? variable.predicate_variable})`;
    })
    .join(" → ");
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

// A dashboard suggestion can take a real while (list_existing_panels, then
// several query_telemetry calls, then suggest_dashboard -- easily 30-60s+
// of actual round-trip time) -- a static "Thinking..." bubble that never
// changes for that long reads as hung, not working. Cycling label text
// plus a slow color shift are both purely cosmetic (there's no way to know
// which real step the model is on from here), but give continuous visual
// feedback that something is still happening.
// Generic on purpose -- this indicator shows during every Co-pilot flow
// (Q&A, automation suggestions, panel suggestions, dashboard suggestions),
// not just dashboard/panel ones, so phrasing like "Checking existing
// panels" or "Visualizing" read as wrong/broken outside that one flow.
const THINKING_PHRASES = [
  "Thinking",
  "Analyzing your data",
  "Checking existing setup",
  "Drafting a proposal",
  "Almost there",
];
const THINKING_PHRASE_INTERVAL_MS = 2200;

function ThinkingIndicator() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setIndex((prev) => (prev + 1) % THINKING_PHRASES.length);
    }, THINKING_PHRASE_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, []);

  return <span className="copilot-chat__thinking">{THINKING_PHRASES[index]}...</span>;
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

  function handleOpenSuggestion(suggestion: Exclude<CopilotSuggestion, { kind: "dashboard" }>) {
    if (suggestion.kind === "panel") {
      navigate(`/dashboards/${suggestion.state.dashboard_id}/panels/new`, { state: suggestion.state });
      return;
    }
    navigate(suggestionRoute(suggestion.kind), { state: suggestion.state });
  }

  // Unlike every other suggestion kind, there's no existing form to
  // navigate into and prefill -- the dashboard doesn't exist yet, and per
  // the product decision behind this feature, review already happened by
  // reading the card (variable chain + panel list) and refining in chat,
  // not by handing the user a further editable form. So this creates the
  // dashboard for real directly: first the shell + variables (one call,
  // relying on Variable's own chain-order validation accepting a whole
  // ordered list at once, same as DashboardService already enforces), then
  // every proposed panel in sequence (not parallel, so each panel's
  // position is computed against the ones already placed earlier in this
  // same batch -- addPanel's response isn't needed for that, the position
  // is decided client-side up front). Panels are bulk-created without a
  // per-panel review gate on purpose -- unlike variables, a panel is
  // read-only with no side effects, trivially deleted/edited afterward via
  // the dashboard's own panel menu.
  async function handleCreateDashboardSuggestion(state: DashboardSuggestionState) {
    if (sending) return;
    updateCopilotSession({ sending: true, error: null });
    try {
      const dashboard = await createDashboard({
        project_id: state.project_id,
        name: state.name,
        description: state.description,
        variables: state.variables,
        panels: [],
        layout: {},
      });
      let placed: { position: PanelPosition }[] = [];
      for (const panel of state.panels) {
        const position = findFreePosition(placed, DEFAULT_POSITION.width, DEFAULT_POSITION.height);
        placed = [...placed, { position }];
        await addPanel(dashboard.id, {
          title: panel.title,
          chart: panel.chart,
          query: panel.query,
          time_range: panel.time_range,
          refresh_interval: 0,
          position,
          event_rule_ids: [],
        });
      }
      navigate(`/dashboards/${dashboard.id}`);
    } catch (err) {
      updateCopilotSession({ error: err instanceof ApiError ? err.message : "Failed to create dashboard." });
    } finally {
      updateCopilotSession({ sending: false });
    }
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
            {ackDone && effectiveIntent === "suggest-dashboard" && messages.length === 0 && (
              <div className="copilot-chat__project-chips">
                <button
                  type="button"
                  className="copilot-chat__project-chip"
                  onClick={() => sendMessage(SUGGEST_DASHBOARD_SEED_REPLY)}
                >
                  {SUGGEST_DASHBOARD_SEED_REPLY}
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
                <button
                  type="button"
                  className="copilot-chat__project-chip"
                  onClick={() => sendMessage(SUGGEST_DASHBOARD_SEED_REPLY)}
                >
                  Suggest a dashboard
                </button>
              </div>
            )}
          </>
        )}

        {messages.map((message, index) => {
          const suggestion = suggestionByIndex[index];
          return (
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
              {suggestion &&
                (suggestion.kind === "dashboard" ? (
                  <div className="copilot-chat__suggestion-card copilot-chat__suggestion-card--dashboard">
                    <span className="copilot-chat__suggestion-label">{suggestion.label}</span>
                    <div className="copilot-chat__suggestion-detail">
                      <strong>Variables:</strong> {describeVariableChain(suggestion.state.variables)}
                    </div>
                    <ul className="copilot-chat__suggestion-panel-list">
                      {suggestion.state.panels.map((panel, panelIndex) => (
                        <li key={panelIndex}>
                          {panel.title}{" "}
                          <span className="copilot-chat__suggestion-panel-type">({panel.chart.type})</span>
                        </li>
                      ))}
                    </ul>
                    <button
                      type="button"
                      className="copilot-chat__suggestion-action"
                      disabled={sending}
                      onClick={() => handleCreateDashboardSuggestion(suggestion.state)}
                    >
                      {sending
                        ? "Creating..."
                        : `Create dashboard (${suggestion.state.panels.length} panel${suggestion.state.panels.length === 1 ? "" : "s"}) →`}
                    </button>
                  </div>
                ) : (
                  <div className="copilot-chat__suggestion-card">
                    <span className="copilot-chat__suggestion-label">{suggestion.label}</span>
                    <button
                      type="button"
                      className="copilot-chat__suggestion-action"
                      onClick={() => handleOpenSuggestion(suggestion)}
                    >
                      Open in builder →
                    </button>
                  </div>
                ))}
            </Fragment>
          );
        })}
        {sending && (
          <div className="copilot-chat__message copilot-chat__message--assistant">
            <ThinkingIndicator />
          </div>
        )}
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
