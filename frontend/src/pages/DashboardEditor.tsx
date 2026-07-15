import { useEffect, useMemo, useState } from "react";
import GridLayout, { WidthProvider } from "react-grid-layout";
import type { Layout } from "react-grid-layout";
import { Link, useNavigate, useParams } from "react-router-dom";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { ApiError } from "../api/client";
import { getDashboard, removePanel, runPanelQuery, saveLayout, updatePanel } from "../api/dashboard";
import { listAutomaters } from "../api/automater";
import { listQueryRules } from "../api/queryRule";
import { listEventsForOverlay } from "../api/event";
import { ChartPreview } from "../components/ChartPreview";
import { MoreIcon, PlusIcon } from "../components/icons";
import { RuleMultiSelect } from "../components/RuleMultiSelect";
import type { RuleOption } from "../components/RuleMultiSelect";
import { TypeaheadSelect } from "../components/TypeaheadSelect";
import { useEvents } from "../context/EventsContext";
import { DEFAULT_REFRESH_INTERVAL, REFRESH_INTERVALS } from "../constants/refreshIntervals";
import { DEFAULT_TIME_RANGE, TIME_RANGES } from "../constants/timeRanges";
import { filterEventsByVariables, resolveVariablesFrom } from "../utils/variables";
import type { Automater } from "../types/automater";
import type { QueryRule } from "../types/queryRule";
import type { Dashboard, Panel, PanelInputPayload, Variable } from "../types/dashboard";
import type { Event } from "../types/event";
import "./Dashboard.css";

const XY_CHART_TYPES = new Set(["line", "bar", "scatter"]);

const ResponsiveGridLayout = WidthProvider(GridLayout);
const GRID_COLUMNS = 12;
const ROW_HEIGHT = 32;

export function DashboardEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [layout, setLayout] = useState<Layout[]>([]);
  const [panelRows, setPanelRows] = useState<Record<string, Record<string, unknown>[]>>({});
  const [panelEvents, setPanelEvents] = useState<Record<string, Event[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [timeRange, setTimeRange] = useState(DEFAULT_TIME_RANGE);
  const [refreshInterval, setRefreshInterval] = useState(DEFAULT_REFRESH_INTERVAL);
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [variableOptions, setVariableOptions] = useState<Record<string, string[]>>({});
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [titleMenuOpen, setTitleMenuOpen] = useState(false);
  const [automaters, setAutomaters] = useState<Automater[]>([]);
  const [queryRules, setQueryRules] = useState<QueryRule[]>([]);
  const { projects, dashboardsByProject, setDefaultDashboard, registerDashboardVariables, clearDashboardVariables } =
    useEvents();

  // Every Rule in this dashboard's project -- both real-time Rules
  // (flattened across that project's Automaters; Rule has no automater/
  // project backreference of its own, mirrors AutomaterEditor.tsx's
  // existing project-scoping pattern) and Query Rules (a separate
  // top-level entity, not nested in an Automater) -- for each panel
  // header's Overlay Events control. `Event.rule_id` is just the
  // producing rule's own id regardless of source (confirmed:
  // EventRepository's pairing/filtering never distinguishes them), so
  // both kinds work as event_rule_ids entries with no backend changes.
  const projectRules: RuleOption[] = useMemo(() => {
    if (!dashboard) return [];
    const realTimeRules = automaters
      .filter((automater) => automater.project_id === dashboard.project_id)
      .flatMap((automater) =>
        automater.rules.map((rule) => ({ id: rule.id, name: rule.name, sourceLabel: automater.name })),
      );
    const scheduledRules = queryRules
      .filter((queryRule) => queryRule.project_id === dashboard.project_id)
      .map((queryRule) => ({ id: queryRule.id, name: queryRule.name, sourceLabel: "Scheduled" }));
    return [...realTimeRules, ...scheduledRules];
  }, [automaters, queryRules, dashboard]);

  useEffect(() => {
    listAutomaters()
      .then(setAutomaters)
      .catch(() => undefined);
    listQueryRules()
      .then(setQueryRules)
      .catch(() => undefined);
  }, []);

  // A fixed-position backdrop can't be used to detect outside clicks here:
  // react-grid-layout positions panels with a CSS `transform`, which makes
  // the panel the containing block for any `position: fixed` descendant,
  // so a backdrop rendered inside a panel never actually covers the
  // viewport. Closing on any click outside `.dashboard-menu` avoids that
  // entirely.
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (!(event.target instanceof Element) || !event.target.closest(".dashboard-menu")) {
        setOpenMenu(null);
        setAddMenuOpen(false);
        setTitleMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function loadDashboard() {
    if (!id) return;
    try {
      const loaded = await getDashboard(id);
      const { values, options } = await resolveVariablesFrom(id, loaded.variables, 0, {});
      setDashboard(loaded);
      setLayout(
        loaded.panels.map((panel) => ({
          i: panel.id,
          x: panel.position.x,
          y: panel.position.y,
          w: panel.position.width,
          h: panel.position.height,
        })),
      );
      setVariableValues(values);
      setVariableOptions(options);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load dashboard.");
    }
  }

  async function handleVariableChange(index: number, value: string) {
    if (!id || !dashboard) return;
    const variable = dashboard.variables[index];
    const baseValues = { ...variableValues, [variable.name]: value };
    const { values, options } = await resolveVariablesFrom(
      id,
      dashboard.variables,
      index + 1,
      baseValues,
    );
    setVariableValues(values);
    setVariableOptions((prev) => ({ ...prev, ...options }));
  }

  // Applies every identifier that matches one of this dashboard's
  // variables (by value_column) at once, re-resolving the predicate
  // chain from the *earliest* matched variable's index -- so e.g. Hive's
  // options get re-resolved against the *new* Apiary value before Hive
  // itself is checked against them, instead of each identifier being
  // applied one at a time against a still-stale predicate. Any
  // identifier whose value still doesn't resolve after that falls back
  // to the first available option (resolveVariablesFrom's own existing
  // behavior, same as a manual dropdown pick that's no longer valid) --
  // not an error, since a genuine mismatch is an expected outcome here,
  // not a bug (see EventsContext's ActiveDashboardVariables comment).
  async function selectIdentifiers(identifiers: Record<string, string>) {
    if (!id || !dashboard) return;
    const matchedUpdates: Record<string, string> = {};
    let earliestIndex = dashboard.variables.length;
    dashboard.variables.forEach((variable, index) => {
      const value = identifiers[variable.value_column];
      if (value === undefined) return;
      matchedUpdates[variable.name] = value;
      earliestIndex = Math.min(earliestIndex, index);
    });
    if (earliestIndex === dashboard.variables.length) return; // nothing matched

    const baseValues = { ...variableValues, ...matchedUpdates };
    const { values, options } = await resolveVariablesFrom(id, dashboard.variables, earliestIndex, baseValues);
    setVariableValues(values);
    setVariableOptions((prev) => ({ ...prev, ...options }));
  }

  // Lets the globally-mounted events panel offer "click an identifier to
  // set the matching dashboard variable(s)" while this dashboard happens
  // to be open -- see EventsContext.tsx's ActiveDashboardVariables
  // comment. Re-registers whenever variables/values change so the
  // events panel always sees this dashboard's current state, not a
  // stale snapshot from whenever it first mounted.
  useEffect(() => {
    if (!dashboard) return;
    registerDashboardVariables({
      dashboardId: dashboard.id,
      projectId: dashboard.project_id,
      variables: dashboard.variables,
      selectIdentifiers,
    });
    return () => clearDashboardVariables(dashboard.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard, variableValues]);

  function refreshPanelData(
    panels: Panel[],
    timeRangeCode: string,
    values: Record<string, string>,
    variables: Variable[],
  ) {
    if (!id) return;
    for (const panel of panels) {
      runPanelQuery(id, panel.id, { time_range: timeRangeCode, variable_values: values })
        .then((result) => {
          setPanelRows((prev) => ({ ...prev, [panel.id]: result.rows }));
          if (panel.event_rule_ids.length === 0) {
            setPanelEvents((prev) => ({ ...prev, [panel.id]: [] }));
            return;
          }
          // Reuses the exact [time_from, time_to] this panel's own query
          // just resolved -- not a separately (and therefore slightly
          // later) resolved "now" -- see iotops-workspace/ROADMAP.md's
          // "Events-as-overlay on Panel charts" note.
          listEventsForOverlay(panel.event_rule_ids, result.time_from, result.time_to)
            .then((events) =>
              setPanelEvents((prev) => ({
                ...prev,
                // Only events that actually belong to whatever the
                // dashboard's variables currently have selected (e.g. a
                // panel scoped to hive-1 shouldn't show hive-2's events
                // just because both share a Rule).
                [panel.id]: filterEventsByVariables(events, variables, values),
              })),
            )
            .catch(() => setPanelEvents((prev) => ({ ...prev, [panel.id]: [] })));
        })
        .catch(() => setPanelRows((prev) => ({ ...prev, [panel.id]: [] })));
    }
  }

  useEffect(() => {
    loadDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (dashboard) {
      refreshPanelData(dashboard.panels, timeRange, variableValues, dashboard.variables);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard, timeRange, variableValues]);

  useEffect(() => {
    if (!dashboard) return;
    const ms = REFRESH_INTERVALS.find((option) => option.code === refreshInterval)?.ms;
    if (!ms) return;
    const intervalId = setInterval(
      () => refreshPanelData(dashboard.panels, timeRange, variableValues, dashboard.variables),
      ms,
    );
    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard, timeRange, variableValues, refreshInterval]);

  async function handleRemovePanel(panelId: string) {
    if (!id) return;
    setOpenMenu(null);
    try {
      await removePanel(id, panelId);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to remove panel.");
    }
  }

  // The Overlay Events selection is saved on the Panel object itself (see
  // iotops-workspace/ROADMAP.md's "Events-as-overlay on Panel charts"
  // note) -- updatePanel is a full PanelInput replace, so every other
  // field has to be resent unchanged alongside the new event_rule_ids.
  async function handlePanelEventRuleIdsChange(panel: Panel, ruleIds: string[]) {
    if (!id || !dashboard) return;
    const payload: PanelInputPayload = {
      title: panel.title,
      chart: panel.chart,
      query: panel.query,
      time_range: panel.time_range,
      refresh_interval: panel.refresh_interval,
      position: panel.position,
      event_rule_ids: ruleIds,
    };
    try {
      const updated = await updatePanel(id, panel.id, payload);
      setDashboard(updated);
      const updatedPanel = updated.panels.find((p) => p.id === panel.id);
      if (updatedPanel) refreshPanelData([updatedPanel], timeRange, variableValues, updated.variables);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update panel.");
    }
  }

  async function handleSaveLayout() {
    if (!id || !dashboard) return;
    setSaving(true);
    try {
      await saveLayout(id, {
        panels: layout.map((item) => ({
          id: item.i,
          position: { x: item.x, y: item.y, width: item.w, height: item.h },
        })),
        layout: dashboard.layout,
      });
      await loadDashboard();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save layout.");
    } finally {
      setSaving(false);
    }
  }

  if (!dashboard) {
    return (
      <main className="collector-page">
        {error ? <p className="collector-page__error">{error}</p> : <p>Loading...</p>}
      </main>
    );
  }

  return (
    <main className="collector-page dashboard-page">
      <div className="dashboard-page__layout">
        <div className="dashboard-page__content">
          <div className="dashboard-toolbar">
            <div className="dashboard-toolbar__left">
              <div className="dashboard-menu">
                <button
                  type="button"
                  className="dashboard-toolbar__control dashboard-toolbar__title"
                  onClick={() => setTitleMenuOpen((open) => !open)}
                >
                  <span className="dashboard-toolbar__title-text">{dashboard.name}</span>
                  <span className="dashboard-toolbar__title-caret">▾</span>
                </button>
                {titleMenuOpen && (
                  <div className="dashboard-menu__list dashboard-menu__list--title">
                    {(dashboardsByProject[dashboard.project_id] ?? []).map((sibling) => {
                      const project = projects.find((p) => p.id === dashboard.project_id);
                      const isDefault = project?.default_dashboard_id === sibling.id;
                      return (
                        <div key={sibling.id} className="dashboard-title-menu__row">
                          <button
                            type="button"
                            className={`dashboard-menu__item ${
                              sibling.id === dashboard.id ? "dashboard-menu__item--current" : ""
                            }`}
                            onClick={() => {
                              setTitleMenuOpen(false);
                              if (sibling.id !== dashboard.id) navigate(`/dashboards/${sibling.id}`);
                            }}
                          >
                            {sibling.name}
                          </button>
                          <button
                            type="button"
                            className={`dashboard-title-menu__star ${
                              isDefault ? "dashboard-title-menu__star--active" : ""
                            }`}
                            title={isDefault ? "Default dashboard for this project" : "Set as default dashboard"}
                            onClick={() => setDefaultDashboard(dashboard.project_id, sibling.id)}
                          >
                            {isDefault ? "★" : "☆"}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              {dashboard.variables.map((variable, index) => (
                <div key={variable.name} className="dashboard-toolbar__variable">
                  <span className="dashboard-toolbar__variable-label">{variable.label}</span>
                  <TypeaheadSelect
                    className="dashboard-toolbar__control"
                    options={variableOptions[variable.name] ?? []}
                    value={variableValues[variable.name] ?? ""}
                    onChange={(value) => handleVariableChange(index, value)}
                  />
                </div>
              ))}
            </div>
            <div className="dashboard-toolbar__actions">
              <select
                className="dashboard-toolbar__control"
                value={timeRange}
                onChange={(event) => setTimeRange(event.target.value)}
              >
                {TIME_RANGES.map((range) => (
                  <option key={range.code} value={range.code}>
                    {range.label}
                  </option>
                ))}
              </select>
    
              <select
                className="dashboard-toolbar__control"
                aria-label="Refresh interval"
                value={refreshInterval}
                onChange={(event) => setRefreshInterval(event.target.value)}
              >
                {REFRESH_INTERVALS.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
    
              <div className="dashboard-menu">
                <button
                  className="dashboard-toolbar__control dashboard-toolbar__control--icon dashboard-toolbar__control--primary"
                  aria-label="Add"
                  onClick={() => setAddMenuOpen((open) => !open)}
                >
                  <PlusIcon />
                </button>
                {addMenuOpen && (
                  <div className="dashboard-menu__list">
                    <Link
                      className="dashboard-menu__item"
                      to={`/dashboards/${id}/panels/new`}
                      onClick={() => setAddMenuOpen(false)}
                    >
                      Add Panel
                    </Link>
                    <Link
                      className="dashboard-menu__item"
                      to={`/dashboards/${id}/variables`}
                      onClick={() => setAddMenuOpen(false)}
                    >
                      Variables
                    </Link>
                  </div>
                )}
              </div>
    
              <button
                className="dashboard-toolbar__control dashboard-toolbar__control--success"
                onClick={handleSaveLayout}
                disabled={saving}
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
    
          {error && <p className="collector-page__error">{error}</p>}
    
          {dashboard.panels.length === 0 ? (
            <div className="collector-page__empty">
              <p>No panels yet. Add one to start visualizing telemetry.</p>
            </div>
          ) : (
            <ResponsiveGridLayout
              className="layout"
              layout={layout}
              cols={GRID_COLUMNS}
              rowHeight={ROW_HEIGHT}
              // react-grid-layout defaults containerPadding to its margin
              // value ([10, 10]) when not set -- insetting every panel row
              // from the grid's own edges, which don't line up with the
              // toolbar's left (title dropdown) and right (Save button)
              // edges above it. Zero it so panels align flush with both.
              containerPadding={[0, 0]}
              draggableHandle=".dashboard-panel__header"
              draggableCancel=".dashboard-panel__menu-trigger, .dashboard-menu__list, .rule-multiselect"
              resizeHandles={["se"]}
              onLayoutChange={setLayout}
            >
              {dashboard.panels.map((panel) => (
                <div key={panel.id} className="dashboard-panel">
                  <div className="dashboard-panel__header">
                    <span className="dashboard-panel__title">{panel.title}</span>
                    <div className="dashboard-panel__header-actions">
                      {XY_CHART_TYPES.has(panel.chart.type) && projectRules.length > 0 && (
                        <RuleMultiSelect
                          compact
                          rules={projectRules}
                          selectedIds={panel.event_rule_ids}
                          onChange={(ruleIds) => handlePanelEventRuleIdsChange(panel, ruleIds)}
                        />
                      )}
                      <div className="dashboard-menu">
                        <button
                          className="dashboard-panel__menu-trigger"
                          aria-label="Panel actions"
                          onClick={() => setOpenMenu((current) => (current === panel.id ? null : panel.id))}
                        >
                          <MoreIcon />
                        </button>
                        {openMenu === panel.id && (
                          <div className="dashboard-menu__list">
                            <button
                              className="dashboard-menu__item"
                              onClick={() => {
                                setOpenMenu(null);
                                navigate(`/dashboards/${id}/panels/${panel.id}/edit`);
                              }}
                            >
                              Edit
                            </button>
                            <button
                              className="dashboard-menu__item dashboard-menu__item--danger"
                              onClick={() => handleRemovePanel(panel.id)}
                            >
                              Remove
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="dashboard-panel__body">
                    <ChartPreview
                      chart={panel.chart}
                      rows={panelRows[panel.id] ?? []}
                      events={panelEvents[panel.id] ?? []}
                      height="100%"
                    />
                  </div>
                </div>
              ))}
            </ResponsiveGridLayout>
          )}
        </div>
      </div>
    </main>
  );
}
