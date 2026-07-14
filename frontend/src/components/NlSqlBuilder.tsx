import { useState } from "react";
import type { RefObject } from "react";
import { ApiError } from "../api/client";

interface NlSqlBuilderProps {
  sql: string;
  onSqlChange: (sql: string) => void;
  // Abstracts over which generation endpoint/prompt framing is used --
  // PanelBuilder's Panel-chart-flavored one (api/ai.ts's generateSql) vs.
  // QueryRuleEditor's match-set-flavored one (generateQueryRuleSql). The
  // NL prompt text itself is passed through so a caller that wants to
  // remember/round-trip it (QueryRuleEditor's nl_prompt field) can capture
  // it from this same callback rather than needing a second prop.
  onGenerate: (prompt: string) => Promise<string>;
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
  hint?: string;
}

export function NlSqlBuilder({ sql, onSqlChange, onGenerate, textareaRef, hint }: NlSqlBuilderProps) {
  const [nlPrompt, setNlPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    if (!nlPrompt.trim()) return;
    setGenerating(true);
    setError(null);
    try {
      const generated = await onGenerate(nlPrompt);
      onSqlChange(generated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate SQL.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <>
      {hint && <p className="wizard-panel__hint">{hint}</p>}
      {error && <p className="collector-page__error">{error}</p>}
      <label className="field" style={{ maxWidth: "none" }}>
        <span>Ask in plain language</span>
        <input
          value={nlPrompt}
          onChange={(event) => setNlPrompt(event.target.value)}
          placeholder="e.g. average temperature per hour for the last day"
        />
      </label>
      <button
        type="button"
        className="button"
        onClick={handleGenerate}
        disabled={generating || !nlPrompt.trim()}
      >
        {generating ? "Generating..." : "Generate SQL"}
      </button>

      <label className="field" style={{ maxWidth: "none", marginTop: 16 }}>
        <span>SQL</span>
        <textarea
          ref={textareaRef}
          className="panel-builder__sql"
          value={sql}
          onChange={(event) => onSqlChange(event.target.value)}
          rows={5}
        />
      </label>
    </>
  );
}
