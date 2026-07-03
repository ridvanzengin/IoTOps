import { useEffect, useState } from "react";
import GridLayout, { WidthProvider } from "react-grid-layout";
import type { Layout } from "react-grid-layout";
import { Link, useNavigate, useParams } from "react-router-dom";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { ApiError } from "../api/client";
import { getDashboard, removePanel, saveLayout } from "../api/dashboard";
import { queryTelemetrySql } from "../api/telemetry";
import { ChartPreview } from "../components/ChartPreview";
import { MoreIcon, PlusIcon } from "../components/icons";
import type { Dashboard } from "../types/dashboard";
import "./Dashboard.css";

const ResponsiveGridLayout = WidthProvider(GridLayout);
const GRID_COLUMNS = 12;
const ROW_HEIGHT = 32;
const TIME_RANGES = ["Last 15m", "Last 1h", "Last 6h", "Last 24h", "Last 7d"];

export function DashboardEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [layout, setLayout] = useState<Layout[]>([]);
  const [panelRows, setPanelRows] = useState<Record<string, Record<string, unknown>[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [timeRange, setTimeRange] = useState(TIME_RANGES[1]);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);

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
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function refresh() {
    if (!id) return;
    try {
      const loaded = await getDashboard(id);
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
      setError(null);

      for (const panel of loaded.panels) {
        queryTelemetrySql({ sql: panel.query.sql, limit: panel.query.limit })
          .then((result) => setPanelRows((prev) => ({ ...prev, [panel.id]: result.rows })))
          .catch(() => setPanelRows((prev) => ({ ...prev, [panel.id]: [] })));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load dashboard.");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function handleRemovePanel(panelId: string) {
    if (!id) return;
    setOpenMenu(null);
    try {
      await removePanel(id, panelId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to remove panel.");
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
      await refresh();
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
      <div className="dashboard-toolbar">
        <div className="dashboard-toolbar__left">
          <h1 className="dashboard-toolbar__title">{dashboard.name}</h1>
          {dashboard.variables.length > 0 && (
            <span className="dashboard-toolbar__variables">
              {dashboard.variables.map((variable) => variable.label).join(", ")}
            </span>
          )}
        </div>
        <div className="dashboard-toolbar__actions">
          <select
            className="dashboard-toolbar__control"
            value={timeRange}
            onChange={(event) => setTimeRange(event.target.value)}
          >
            {TIME_RANGES.map((range) => (
              <option key={range} value={range}>
                {range}
              </option>
            ))}
          </select>

          <div className="dashboard-menu">
            <button
              className="dashboard-toolbar__control dashboard-toolbar__control--icon"
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
                <span className="dashboard-menu__item dashboard-menu__item--disabled">
                  Add Variable <em>Soon</em>
                </span>
              </div>
            )}
          </div>

          <button
            className="dashboard-toolbar__control dashboard-toolbar__control--primary"
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
          draggableHandle=".dashboard-panel__header"
          draggableCancel=".dashboard-panel__menu-trigger, .dashboard-menu__list"
          resizeHandles={["se"]}
          onLayoutChange={setLayout}
        >
          {dashboard.panels.map((panel) => (
            <div key={panel.id} className="dashboard-panel">
              <div className="dashboard-panel__header">
                <span className="dashboard-panel__title">{panel.title}</span>
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
              <div className="dashboard-panel__body">
                <ChartPreview chart={panel.chart} rows={panelRows[panel.id] ?? []} height="100%" />
              </div>
            </div>
          ))}
        </ResponsiveGridLayout>
      )}
    </main>
  );
}
