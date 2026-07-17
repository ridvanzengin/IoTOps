import { Fragment, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { askCopilot } from "../api/ai";
import { ApiError } from "../api/client";
import { useEvents } from "../context/EventsContext";
import type { Project } from "../types/project";
import type { CopilotIntent, CopilotMessage, CopilotSuggestion, NeedsContext } from "../types/ai";
import "./CopilotChat.css";

const ASSISTANT_NAME = "ARIA";
const TYPE_SPEED_MS = 16;

// A single tap to kick off the suggest-automation flow without typing --
// the button's own label doubles as the message it sends, so there's one
// string to keep in sync, not a short label plus a separate long message.
const SUGGEST_AUTOMATION_SEED_REPLY = "Analyze my telemetry and suggest an automation";

function greetingText(intent?: CopilotIntent): string {
  if (intent === "suggest-automation") {
    return `Hi, I'm ${ASSISTANT_NAME}. Which project would you like to set up an automation for?`;
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
  return `How can I help you with ${project.name}?`;
}

function suggestionRoute(kind: CopilotSuggestion["kind"]): string {
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

// Self-contained, mirrors NlSqlBuilder.tsx's pattern -- no context needed
// beyond `projects` (already exposed by useEvents(), same as EventsPanel
// itself reads). The multi-tool-call loop happens entirely server-side; this
// component only ever sees the flat {role, content} transcript for the real
// conversation -- the greeting/project-pick/acknowledgement above it is a
// scripted, client-only sequence, never sent to the backend as history.
export function CopilotChat({ intent }: { intent?: CopilotIntent }) {
  const { projects } = useEvents();
  const navigate = useNavigate();
  const [greetingDone, setGreetingDone] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [ackDone, setAckDone] = useState(false);
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  // Keyed by index into `messages` -- rendering-only, never sent as part of
  // the history payload (CopilotMessage itself stays {role, content}).
  const [needsContextByIndex, setNeedsContextByIndex] = useState<Record<number, NeedsContext>>({});
  const [suggestionByIndex, setSuggestionByIndex] = useState<Record<number, CopilotSuggestion>>({});
  // Only ever rendered for the latest message (see the render loop below)
  // -- unlike needsContext/suggestion, a quick-reply is "waiting for your
  // input right now", not a persistent artifact worth re-showing once the
  // conversation has moved past it.
  const [quickRepliesByIndex, setQuickRepliesByIndex] = useState<Record<number, string[]>>({});
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, greetingDone, project, ackDone, sending]);

  function handleSelectProject(next: Project) {
    // A new project is a new conversation -- avoids a transcript that
    // silently mixes which project's data grounds the answers.
    setProject(next);
    setAckDone(false);
    setMessages([]);
    setNeedsContextByIndex({});
    setSuggestionByIndex({});
    setQuickRepliesByIndex({});
    setError(null);
  }

  async function sendMessage(question: string) {
    if (!project || !question.trim() || sending) return;
    const nextMessages: CopilotMessage[] = [...messages, { role: "user", content: question }];
    setMessages(nextMessages);
    setInput("");
    setSending(true);
    setError(null);
    try {
      const { answer, needs_context, suggestion, quick_replies } = await askCopilot(
        project.id,
        question,
        nextMessages.slice(-8),
      );
      const answerIndex = nextMessages.length;
      // `answer` may carry a trailing machine-readable recap (stripped only
      // at render time, see renderAssistantContent) -- stored as-is here
      // since this is exactly what round-trips as history on the next turn.
      setMessages((prev) => [...prev, { role: "assistant", content: answer }]);
      if (needs_context) {
        setNeedsContextByIndex((prev) => ({ ...prev, [answerIndex]: needs_context }));
      }
      if (suggestion) {
        setSuggestionByIndex((prev) => ({ ...prev, [answerIndex]: suggestion }));
      }
      if (quick_replies) {
        setQuickRepliesByIndex((prev) => ({ ...prev, [answerIndex]: quick_replies }));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to get an answer.");
    } finally {
      setSending(false);
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
    navigate(suggestionRoute(suggestion.kind), { state: suggestion.state });
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") handleSend();
  }

  const chatting = project !== null && ackDone;

  return (
    <div className="copilot-chat">
      <div ref={listRef} className="copilot-chat__messages">
        <div className="copilot-chat__message copilot-chat__message--assistant">
          {greetingDone ? (
            greetingText(intent)
          ) : (
            <TypedLine text={greetingText(intent)} onDone={() => setGreetingDone(true)} />
          )}
        </div>

        {greetingDone && !project && (
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
            <div className="copilot-chat__message copilot-chat__message--user">{project.name}</div>
            <div className="copilot-chat__message copilot-chat__message--assistant">
              {ackDone ? (
                ackText(project, intent)
              ) : (
                <TypedLine
                  key={project.id}
                  text={ackText(project, intent)}
                  onDone={() => setAckDone(true)}
                />
              )}
            </div>
            {ackDone && intent === "suggest-automation" && messages.length === 0 && (
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
          onChange={(event) => setInput(event.target.value)}
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
