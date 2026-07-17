import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { deleteQueryRule, listQueryRules, updateQueryRule } from "../api/queryRule";
import { listProjects } from "../api/project";
import { CopilotIcon, MoreIcon } from "../components/icons";
import { useEvents } from "../context/EventsContext";
import type { QueryRule } from "../types/queryRule";
import type { Project } from "../types/project";
import "./Collector.css";
import "./QueryRuleList.css";

function scheduleSummary(rule: QueryRule): string {
  return rule.schedule.interval ? `every ${rule.schedule.interval}` : `cron ${rule.schedule.cron}`;
}

export function QueryRuleList() {
  const { openCopilotPanel } = useEvents();
  const [queryRules, setQueryRules] = useState<QueryRule[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (!(event.target instanceof Element) || !event.target.closest(".dropdown-menu")) {
        setOpenMenu(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function projectName(projectId: string): string {
    return projects.find((project) => project.id === projectId)?.name ?? "—";
  }

  async function refresh() {
    try {
      setQueryRules(await listQueryRules());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load query rules.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    listProjects()
      .then(setProjects)
      .catch(() => undefined);
  }, []);

  async function withPending(key: string, action: () => Promise<unknown>) {
    setPendingKey(key);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setPendingKey(null);
    }
  }

  function toggleEnabled(rule: QueryRule) {
    if (rule.enabled && !window.confirm(`Disable query rule "${rule.name}"? It will stop evaluating.`)) {
      return;
    }
    return withPending(rule.id, () =>
      updateQueryRule(rule.id, {
        project_id: rule.project_id,
        name: rule.name,
        description: rule.description,
        sql: rule.sql,
        nl_prompt: rule.nl_prompt,
        identifiers: rule.identifiers,
        category: rule.category,
        severity: rule.severity,
        event_type: rule.event_type,
        message: rule.message,
        resolve_mode: rule.resolve_mode,
        schedule: rule.schedule,
        enabled: !rule.enabled,
      }),
    );
  }

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <h1>Scheduled Rules</h1>
        <div className="collector-page__header-actions">
          <button
            type="button"
            className="button button--primary"
            onClick={() => openCopilotPanel("suggest-automation")}
          >
            <CopilotIcon width={16} height={16} />
            Ask AI
          </button>
          <Link className="button button--success" to="/query-rules/new">
            + New Rule
          </Link>
        </div>
      </div>

      {error && <p className="collector-page__error">{error}</p>}

      {loading ? (
        <p>Loading...</p>
      ) : queryRules.length === 0 ? (
        <div className="collector-page__empty">
          <p>
            No query rules yet. Create one to detect conditions a real-time rule can't express —
            cross-table joins, time-windowed aggregates — evaluated on a schedule.
          </p>
        </div>
      ) : (
        <div className="collector-card">
          <table className="collector-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Project</th>
                <th>Identifiers</th>
                <th>Severity</th>
                <th>Schedule</th>
                <th>Last Evaluated</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {queryRules.map((rule) => (
                <tr key={rule.id}>
                  <td>{rule.name}</td>
                  <td>{projectName(rule.project_id)}</td>
                  <td className="query-rule-list__identifiers">{rule.identifiers.join(", ")}</td>
                  <td>{rule.severity}</td>
                  <td>{scheduleSummary(rule)}</td>
                  <td>{rule.last_evaluated_at ? new Date(rule.last_evaluated_at).toLocaleString() : "Never"}</td>
                  <td>
                    <span
                      className={`query-rule-list__status query-rule-list__status--${rule.enabled ? "active" : "inactive"}`}
                    >
                      {rule.enabled ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="collector-table__actions">
                    <button className="button" disabled={pendingKey === rule.id} onClick={() => toggleEnabled(rule)}>
                      {rule.enabled ? "Disable" : "Enable"}
                    </button>
                    <div className="dropdown-menu">
                      <button
                        type="button"
                        className="dropdown-menu__trigger"
                        aria-label="Rule actions"
                        aria-expanded={openMenu === rule.id}
                        onClick={() => setOpenMenu((current) => (current === rule.id ? null : rule.id))}
                      >
                        <MoreIcon />
                      </button>
                      {openMenu === rule.id && (
                        <div className="dropdown-menu__list">
                          <button
                            type="button"
                            className="dropdown-menu__item dropdown-menu__item--danger"
                            disabled={pendingKey === rule.id}
                            onClick={() => {
                              setOpenMenu(null);
                              if (!window.confirm(`Delete query rule "${rule.name}"? This cannot be undone.`)) return;
                              withPending(rule.id, () => deleteQueryRule(rule.id));
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
