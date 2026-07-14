import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { generateQueryRuleSql } from "../api/ai";
import { ApiError } from "../api/client";
import { createQueryRule, previewQueryRule } from "../api/queryRule";
import { listProjects } from "../api/project";
import { NlSqlBuilder } from "../components/NlSqlBuilder";
import { SchemaBrowser } from "../components/SchemaBrowser";
import type { QueryRuleInput } from "../types/queryRule";
import type { ResolveMode, RuleSeverity } from "../types/automater";
import type { Project } from "../types/project";
import type { TelemetrySqlQueryResult } from "../types/telemetry";
import "./Collector.css";
import "./AutomaterEditor.css";
import "./PanelBuilder.css";

const RULE_SEVERITIES: RuleSeverity[] = ["low", "medium", "high", "critical"];
const RESOLVE_MODES: ResolveMode[] = ["auto", "manual"];
// Common cadences -- a scheduled query re-runs unattended, so a small
// curated set of sane values beats a freeform field a typo can silently
// break. Cron (below) is the escape hatch for anything finer-grained or
// calendar-based.
const INTERVAL_PRESETS = ["1m", "5m", "10m", "15m", "30m", "1h", "3h", "6h", "12h", "24h"];

type ScheduleMode = "interval" | "cron";

export function QueryRuleEditor() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [eventType, setEventType] = useState("");
  const [severity, setSeverity] = useState<RuleSeverity>("low");
  const [message, setMessage] = useState("");
  const [identifiers, setIdentifiers] = useState<string[]>([]);
  const [resolveMode, setResolveMode] = useState<ResolveMode>("auto");

  const [scheduleMode, setScheduleMode] = useState<ScheduleMode>("interval");
  const [interval, setInterval] = useState("5m");
  const [cron, setCron] = useState("");

  const [sql, setSql] = useState("SELECT ");
  const [nlPrompt, setNlPrompt] = useState<string | null>(null);
  const [showSchema, setShowSchema] = useState(false);

  const [previewResult, setPreviewResult] = useState<TelemetrySqlQueryResult | null>(null);
  const [previewRunning, setPreviewRunning] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setLoadError("Failed to load available projects."));
  }, []);

  async function handleGenerate(prompt: string): Promise<string> {
    setNlPrompt(prompt);
    const { sql: generated } = await generateQueryRuleSql(prompt, identifiers);
    return generated;
  }

  async function runPreview() {
    setPreviewRunning(true);
    setPreviewError(null);
    try {
      setPreviewResult(await previewQueryRule(sql));
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : "Query failed.");
      setPreviewResult(null);
    } finally {
      setPreviewRunning(false);
    }
  }

  function canSubmit(): boolean {
    const scheduleValid = scheduleMode === "interval" ? interval.trim().length > 0 : cron.trim().length > 0;
    return projectId.length > 0 && name.trim().length > 0 && sql.trim().length > "SELECT".length && scheduleValid;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    const payload: QueryRuleInput = {
      project_id: projectId,
      name,
      description: "",
      sql,
      nl_prompt: nlPrompt,
      identifiers,
      category,
      severity,
      event_type: eventType,
      message,
      resolve_mode: resolveMode,
      schedule:
        scheduleMode === "interval" ? { interval, cron: null } : { interval: null, cron },
      enabled: true,
    };

    setSubmitting(true);
    try {
      await createQueryRule(payload);
      navigate("/query-rules");
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Failed to create query rule.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <h1>New Scheduled Rule</h1>
      </div>
      <p style={{ margin: "-16px 0 24px", color: "var(--text)" }}>
        A SQL query re-run on its own schedule directly against TimescaleDB — for conditions a
        real-time rule can't express: cross-table joins, time-windowed aggregates (e.g. "last 1h
        average"). Author it by hand or describe it in plain language on the right.
      </p>

      {loadError && <p className="collector-page__error">{loadError}</p>}
      {submitError && <p className="collector-page__error">{submitError}</p>}

      <form onSubmit={handleSubmit}>
        <div className="automater-editor__grid">
          <div className="wizard-panel">
            <h2 className="wizard-panel__title">Where this rule lives</h2>
            <label className="field">
              <span>Project</span>
              <select value={projectId} onChange={(event) => setProjectId(event.target.value)} required>
                <option value="">Select a project</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>

            <h2 className="wizard-panel__title" style={{ marginTop: 24 }}>
              Rule
            </h2>
            <div className="automater-editor__field-grid">
              <label className="field">
                <span>Rule Name</span>
                <input value={name} onChange={(event) => setName(event.target.value)} required />
              </label>
              <label className="field">
                <span>Severity</span>
                <select value={severity} onChange={(event) => setSeverity(event.target.value as RuleSeverity)}>
                  {RULE_SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Category</span>
                <input value={category} onChange={(event) => setCategory(event.target.value)} />
              </label>
              <label className="field">
                <span>Event Type</span>
                <input value={eventType} onChange={(event) => setEventType(event.target.value)} />
              </label>
              <label className="field">
                <span>Identifiers (optional)</span>
                <input
                  key={identifiers.join(",")}
                  defaultValue={identifiers.join(", ")}
                  placeholder="station_id"
                  onBlur={(event) =>
                    setIdentifiers(
                      event.target.value
                        .split(",")
                        .map((item) => item.trim())
                        .filter((item) => item.length > 0),
                    )
                  }
                />
              </label>
              <label className="field">
                <span>Resolution</span>
                <select value={resolveMode} onChange={(event) => setResolveMode(event.target.value as ResolveMode)}>
                  {RESOLVE_MODES.map((mode) => (
                    <option key={mode} value={mode}>
                      {mode === "auto" ? "Auto-resolve" : "Manual-resolve"}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="wizard-panel__hint">
              Which of the query's selected columns identify one matching entity (e.g. a device or
              station) — every result row is grouped by these values to tell a new match from a
              still-open one. Leave empty to treat the whole query as a single system-wide check
              instead — every matching row then shares one occurrence, same as a real-time Rule
              with no identifiers.
            </p>
            {resolveMode === "manual" && (
              <p className="automater-editor__warning" style={{ marginTop: -8 }}>
                This rule will never auto-clear -- a matching occurrence stays active until someone
                resolves it from the Events sidebar.
              </p>
            )}

            <div className="automater-editor__field-grid" style={{ marginTop: 8 }}>
              <label className="field" style={{ gridColumn: scheduleMode === "interval" ? "1" : "1 / -1" }}>
                <span>Schedule</span>
                {scheduleMode === "interval" ? (
                  <select value={interval} onChange={(event) => setInterval(event.target.value)}>
                    {INTERVAL_PRESETS.map((preset) => (
                      <option key={preset} value={preset}>
                        every {preset}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={cron}
                    placeholder="0 3 * * *  (daily at 3am)"
                    onChange={(event) => setCron(event.target.value)}
                  />
                )}
              </label>
              {scheduleMode === "interval" && (
                <div className="field" style={{ alignSelf: "end", paddingBottom: 8 }}>
                  <span style={{ visibility: "hidden" }}>Advanced</span>
                  <button type="button" className="button" onClick={() => setScheduleMode("cron")}>
                    Advanced: use cron
                  </button>
                </div>
              )}
            </div>
            {scheduleMode === "cron" && (
              <button
                type="button"
                className="button"
                style={{ marginTop: -8, marginBottom: 16 }}
                onClick={() => setScheduleMode("interval")}
              >
                Use a simple interval instead
              </button>
            )}

            <label className="field">
              <span>Message</span>
              <textarea rows={3} value={message} onChange={(event) => setMessage(event.target.value)} />
            </label>

            <div className="wizard-actions">
              <button type="button" className="button" onClick={() => navigate("/query-rules")}>
                Cancel
              </button>
              <button type="submit" className="button button--primary" disabled={!canSubmit() || submitting}>
                {submitting ? "Creating..." : "Create Rule"}
              </button>
            </div>
          </div>

          <div className="panel-builder__column">
            <div className="wizard-panel">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <h2 className="wizard-panel__title" style={{ margin: 0 }}>
                  DB Schema
                </h2>
                <button type="button" className="button" onClick={() => setShowSchema((visible) => !visible)}>
                  {showSchema ? "Hide tables" : "Show tables"}
                </button>
              </div>
              {showSchema && <SchemaBrowser />}
            </div>

            <div className="wizard-panel">
              <h2 className="wizard-panel__title">Query</h2>
              <NlSqlBuilder
                sql={sql}
                onSqlChange={setSql}
                onGenerate={handleGenerate}
                hint="One row per matching entity, e.g. GROUP BY station_id HAVING AVG(wind_speed_kmh) > 30. Time windows are relative and hardcoded (now() - interval '5 minutes'), not tied to any dashboard time range."
              />
              <button
                type="button"
                className="button button--primary"
                onClick={runPreview}
                disabled={previewRunning || sql.trim().length <= "SELECT".length}
              >
                {previewRunning ? "Running..." : "Run Query"}
              </button>
              {previewError && <p className="collector-page__error">{previewError}</p>}
              {previewResult && (
                <div className="panel-builder__results">
                  <table className="collector-table">
                    <thead>
                      <tr>
                        {previewResult.columns.map((column) => (
                          <th key={column}>{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {previewResult.rows.slice(0, 5).map((row, index) => (
                        <tr key={index}>
                          {previewResult.columns.map((column) => (
                            <td key={column}>{String(row[column])}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {previewResult.rows.length === 0 && (
                    <p className="wizard-panel__hint">No rows currently match.</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </form>
    </main>
  );
}
