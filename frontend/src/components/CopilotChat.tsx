import { useEffect, useRef, useState } from "react";
import { askCopilot } from "../api/ai";
import { ApiError } from "../api/client";
import { useEvents } from "../context/EventsContext";
import type { Project } from "../types/project";
import type { CopilotMessage } from "../types/ai";
import "./CopilotChat.css";

const ASSISTANT_NAME = "ARIA";
const GREETING = `Hi, I'm ${ASSISTANT_NAME} — your IoTOps assistant. Which project do you need help with today?`;
const TYPE_SPEED_MS = 16;

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
export function CopilotChat() {
  const { projects } = useEvents();
  const [greetingDone, setGreetingDone] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [ackDone, setAckDone] = useState(false);
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
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
    setError(null);
  }

  async function handleSend() {
    if (!project || !input.trim() || sending) return;
    const question = input.trim();
    const nextMessages: CopilotMessage[] = [...messages, { role: "user", content: question }];
    setMessages(nextMessages);
    setInput("");
    setSending(true);
    setError(null);
    try {
      const { answer } = await askCopilot(project.id, question, nextMessages.slice(-8));
      setMessages((prev) => [...prev, { role: "assistant", content: answer }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to get an answer.");
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") handleSend();
  }

  const chatting = project !== null && ackDone;

  return (
    <div className="copilot-chat">
      <div ref={listRef} className="copilot-chat__messages">
        <div className="copilot-chat__message copilot-chat__message--assistant">
          {greetingDone ? GREETING : <TypedLine text={GREETING} onDone={() => setGreetingDone(true)} />}
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
                `How can I help you with ${project.name}?`
              ) : (
                <TypedLine
                  key={project.id}
                  text={`How can I help you with ${project.name}?`}
                  onDone={() => setAckDone(true)}
                />
              )}
            </div>
          </>
        )}

        {messages.map((message, index) => (
          <div key={index} className={`copilot-chat__message copilot-chat__message--${message.role}`}>
            {message.content}
          </div>
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
