import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { generateSql } from "../api/ai";
import { addPanel, getDashboard, previewDashboardQuery, updatePanel } from "../api/dashboard";
import { ApiError } from "../api/client";
import { ChartPreview } from "../components/ChartPreview";
import { defaultChartForType, PanelEditor } from "../components/PanelEditor";
import { SchemaBrowser } from "../components/SchemaBrowser";
import { DEFAULT_TIME_RANGE } from "../constants/timeRanges";
import { resolveVariablesFrom } from "../utils/variables";
import type { Chart, Panel, PanelPosition, Variable } from "../types/dashboard";
import type { TelemetrySqlQueryResult } from "../types/telemetry";
import "./Collector.css";
import "./PanelBuilder.css";

const DEFAULT_POSITION: PanelPosition = { x: 0, y: 0, width: 6, height: 8 };
const GRID_COLUMNS = 12;

// Best-effort text insertion, not a SQL parser — consistent with how this app
// already treats panel SQL as macro-substitutable text rather than an AST.
// Inserts before the first ORDER BY/GROUP BY/LIMIT clause (or at the end if
// none), adding AND when a WHERE already precedes the insertion point.
function appendWhereClause(sql: string, clause: string): string {
  const trailingMatch = sql.match(/\b(ORDER BY|GROUP BY|LIMIT)\b/i);
  const insertionPoint = trailingMatch ? trailingMatch.index! : sql.length;
  const before = sql.slice(0, insertionPoint).trimEnd();
  const after = sql.slice(insertionPoint);
  const hasWhere = /\bWHERE\b/i.test(before);
  const fragment = hasWhere ? `AND ${clause}` : `WHERE ${clause}`;
  return `${before} ${fragment} ${after}`.trimEnd();
}

function positionsOverlap(a: PanelPosition, b: PanelPosition): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  );
}

// First-fit shelf packing: try each existing row (y = 0, or just below any
// panel) left-to-right before falling back to a new row underneath
// everything, so a new panel lands in an empty slot beside existing panels
// rather than always starting a fresh row.
function findFreePosition(panels: Panel[], width: number, height: number): PanelPosition {
  const candidateYs = [0, ...panels.map((panel) => panel.position.y + panel.position.height)];
  const sortedYs = Array.from(new Set(candidateYs)).sort((a, b) => a - b);

  for (const y of sortedYs) {
    for (let x = 0; x + width <= GRID_COLUMNS; x++) {
      const candidate: PanelPosition = { x, y, width, height };
      if (!panels.some((panel) => positionsOverlap(candidate, panel.position))) {
        return candidate;
      }
    }
  }

  const bottom = panels.reduce((max, panel) => Math.max(max, panel.position.y + panel.position.height), 0);
  return { x: 0, y: bottom, width, height };
}

export function PanelBuilder() {
  const { dashboardId, panelId } = useParams<{ dashboardId: string; panelId?: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(panelId);

  const [title, setTitle] = useState("");
  const [chart, setChart] = useState<Chart>(defaultChartForType("line", ""));
  const [position, setPosition] = useState<PanelPosition>(DEFAULT_POSITION);
  const [timeRange, setTimeRange] = useState(DEFAULT_TIME_RANGE);
  const [variables, setVariables] = useState<Variable[]>([]);
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [nlPrompt, setNlPrompt] = useState("");
  const [sql, setSql] = useState("SELECT * FROM ");
  const [result, setResult] = useState<TelemetrySqlQueryResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Not editable here -- the Overlay Events control lives on the
  // dashboard panel header instead (see DashboardEditor.tsx) -- but this
  // form still has to round-trip whatever's already on the panel, since
  // handleSave below does a full PanelInput replace; without tracking it
  // here, saving any other field from this page would silently wipe an
  // existing panel's event_rule_ids back to [].
  const [eventRuleIds, setEventRuleIds] = useState<string[]>([]);
  const sqlTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  function insertAtCursor(token: string) {
    const textarea = sqlTextareaRef.current;
    const cursor = textarea?.selectionStart ?? sql.length;
    const next = `${sql.slice(0, cursor)}${token}${sql.slice(cursor)}`;
    setSql(next);
    requestAnimationFrame(() => {
      textarea?.focus();
      textarea?.setSelectionRange(cursor + token.length, cursor + token.length);
    });
  }

  function insertVariableFilter(variable: Variable) {
    if (sql.includes(`$${variable.name}`)) return; // already referenced, don't duplicate
    setSql((prev) => appendWhereClause(prev, `${variable.value_column} = $${variable.name}`));
  }

  useEffect(() => {
    if (!dashboardId) return;
    getDashboard(dashboardId)
      .then(async (dashboard) => {
        setVariables(dashboard.variables);
        const { values } = await resolveVariablesFrom(dashboardId, dashboard.variables, 0, {});
        setVariableValues(values);

        if (panelId) {
          const panel = dashboard.panels.find((p) => p.id === panelId);
          if (!panel) {
            setError("Panel not found.");
            return;
          }
          setTitle(panel.title);
          setChart(panel.chart);
          setPosition(panel.position);
          setTimeRange(panel.time_range);
          setSql(panel.query.sql);
          setEventRuleIds(panel.event_rule_ids);
          runQuery(panel.query.sql, panel.time_range, values);
        } else {
          setPosition(findFreePosition(dashboard.panels, DEFAULT_POSITION.width, DEFAULT_POSITION.height));
        }
      })
      .catch(() => setError("Failed to load dashboard."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardId, panelId]);

  async function handleGenerateSql() {
    if (!nlPrompt.trim()) return;
    setGenerating(true);
    setError(null);
    try {
      const { sql: generated } = await generateSql(
        nlPrompt,
        variables.map((v) => ({ name: v.name, label: v.label })),
      );
      setSql(generated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate SQL.");
    } finally {
      setGenerating(false);
    }
  }

  async function runQuery(query: string, timeRangeOverride?: string, variableValuesOverride?: Record<string, string>) {
    if (!dashboardId) return;
    setRunning(true);
    setError(null);
    try {
      const queryResult = await previewDashboardQuery(dashboardId, {
        sql: query,
        limit: 100,
        time_range: timeRangeOverride ?? timeRange,
        variable_values: variableValuesOverride ?? variableValues,
      });
      setResult(queryResult);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Query failed.");
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  async function handleSave() {
    if (!dashboardId) return;
    setSaving(true);
    setError(null);
    try {
      const payload = {
        title,
        chart,
        query: { sql, variables: {}, limit: 1000, timezone: "UTC" },
        time_range: timeRange,
        refresh_interval: 0,
        position,
        event_rule_ids: eventRuleIds,
      };
      if (isEdit && panelId) {
        await updatePanel(dashboardId, panelId, payload);
      } else {
        await addPanel(dashboardId, payload);
      }
      navigate(`/dashboards/${dashboardId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save panel.");
    } finally {
      setSaving(false);
    }
  }

  const columns = result?.columns ?? [];

  return (
    <main className="collector-page panel-builder-page">
      <h1>{isEdit ? "Edit Panel" : "New Panel"}</h1>
      <p style={{ margin: "8px 0 24px", color: "var(--text)" }}>
        Describe what you want in plain language, generate SQL, then pick a chart.
      </p>

      {error && <p className="collector-page__error">{error}</p>}

      <div className="panel-builder">
        <div className="panel-builder__column">
          <div className="wizard-panel">
            <h2 className="wizard-panel__title">Preview</h2>
            <ChartPreview chart={chart} rows={result?.rows ?? []} />
          </div>

          <div className="wizard-panel">
            <h2 className="wizard-panel__title">Query</h2>
            <p className="wizard-panel__hint">
              No manual query builder here &mdash; describe the data you want and generate SQL, or
              hand-edit it directly.
            </p>
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
              onClick={handleGenerateSql}
              disabled={generating || !nlPrompt.trim()}
            >
              {generating ? "Generating..." : "Generate SQL"}
            </button>

            <label className="field" style={{ maxWidth: "none", marginTop: 16 }}>
              <span>SQL</span>
              <textarea
                ref={sqlTextareaRef}
                className="panel-builder__sql"
                value={sql}
                onChange={(event) => setSql(event.target.value)}
                rows={5}
              />
            </label>
            <button
              type="button"
              className="button button--primary"
              onClick={() => runQuery(sql)}
              disabled={running}
            >
              {running ? "Running..." : "Run"}
            </button>

            {result && (
              <div className="panel-builder__results">
                <table className="collector-table">
                  <thead>
                    <tr>
                      {result.columns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.slice(0, 5).map((row, index) => (
                      <tr key={index}>
                        {result.columns.map((column) => (
                          <td key={column}>{String(row[column])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="panel-builder__column">
          <div className="wizard-panel">
            <h2 className="wizard-panel__title">DB Schema</h2>
            <p className="wizard-panel__hint">Click a column to insert it into the SQL box.</p>
            <SchemaBrowser onSelect={insertAtCursor} />
          </div>

          <div className="wizard-panel">
            <h2 className="wizard-panel__title">Panel Configuration</h2>
            <PanelEditor
              title={title}
              onTitleChange={setTitle}
              chart={chart}
              onChartChange={setChart}
              columns={columns}
              timeRange={timeRange}
              onTimeRangeChange={setTimeRange}
              variables={variables}
              onSelectVariableFilter={insertVariableFilter}
            />
          </div>
        </div>
      </div>

      <div className="wizard-actions">
        <button type="button" className="button" onClick={() => navigate(`/dashboards/${dashboardId}`)}>
          Cancel
        </button>
        <button type="button" className="button button--primary" onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Panel"}
        </button>
      </div>
    </main>
  );
}
