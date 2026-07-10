import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  deleteAutomater,
  deleteRule,
  deployAutomater,
  listAutomaters,
  setRuleEnabled,
  stopAutomaterDeployment,
} from "../api/automater";
import { listProjects } from "../api/project";
import { StatusBadge } from "../components/StatusBadge";
import type { Automater, Rule } from "../types/automater";
import type { Project } from "../types/project";
import "./Collector.css";
import "./AutomaterList.css";

function conditionsSummary(rule: Rule): string {
  // Conditions fold left-to-right (see rule.go) -- each condition after
  // the first is prefixed with its own join, since chains can mix AND/OR
  // ("a==1 AND b>3 OR c<5"), not just one operator for the whole rule.
  return rule.conditions
    .map((c, i) => (i === 0 ? "" : `${c.join} `) + `${c.column} ${c.operator} ${String(c.value)}`)
    .join(" ");
}

export function AutomaterList() {
  const [automaters, setAutomaters] = useState<Automater[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);

  function projectName(projectId: string): string {
    return projects.find((project) => project.id === projectId)?.name ?? "—";
  }

  async function refresh() {
    try {
      setAutomaters(await listAutomaters());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load automaters.");
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

  function toggleRuleEnabled(automater: Automater, rule: Rule) {
    if (
      rule.enabled &&
      !window.confirm(`Deactivate rule "${rule.name}"? Its Automater will redeploy without it.`)
    ) {
      return;
    }
    return withPending(`rule-${rule.id}`, () => setRuleEnabled(automater.id, rule.id, !rule.enabled));
  }

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <h1>Automaters</h1>
        <Link className="button button--primary" to="/automaters/new">
          + New Rule
        </Link>
      </div>

      {error && <p className="collector-page__error">{error}</p>}

      {loading ? (
        <p>Loading...</p>
      ) : automaters.length === 0 ? (
        <div className="collector-page__empty">
          <p>No automaters yet. Create a rule to start detecting events from your telemetry.</p>
        </div>
      ) : (
        <div className="automater-list">
          {automaters.map((automater) => (
            <div className="collector-card automater-list__card" key={automater.id}>
              <div className="automater-list__header">
                <div>
                  <strong>{automater.name}</strong>
                  <span className="automater-list__project">{projectName(automater.project_id)}</span>
                  <StatusBadge status={automater.status} />
                </div>
                <div className="collector-table__actions">
                  {automater.status === "running" ? (
                    <button
                      className="button"
                      disabled={pendingKey === automater.id}
                      onClick={() => {
                        if (!window.confirm(`Stop Automater "${automater.name}"? Its rules will stop evaluating.`)) {
                          return;
                        }
                        withPending(automater.id, () => stopAutomaterDeployment(automater.id));
                      }}
                    >
                      Stop
                    </button>
                  ) : (
                    <button
                      className="button"
                      disabled={pendingKey === automater.id}
                      onClick={() => withPending(automater.id, () => deployAutomater(automater.id))}
                    >
                      Deploy
                    </button>
                  )}
                  <button
                    className="button button--danger"
                    disabled={pendingKey === automater.id}
                    onClick={() => {
                      if (
                        !window.confirm(
                          `Delete Automater "${automater.name}" and all ${automater.rules.length} of its rule(s)? This cannot be undone.`,
                        )
                      ) {
                        return;
                      }
                      withPending(automater.id, () => deleteAutomater(automater.id));
                    }}
                  >
                    Delete Automater
                  </button>
                </div>
              </div>

              <table className="collector-table">
                <thead>
                  <tr>
                    <th>Rule</th>
                    <th>Table</th>
                    <th>Conditions</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {automater.rules.map((rule) => (
                    <tr key={rule.id}>
                      <td>{rule.name}</td>
                      <td>{rule.table}</td>
                      <td className="automater-list__conditions">{conditionsSummary(rule)}</td>
                      <td>{rule.severity}</td>
                      <td>
                        <span className={`automater-list__rule-status automater-list__rule-status--${rule.enabled ? "active" : "inactive"}`}>
                          {rule.enabled ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="collector-table__actions">
                        <button
                          className="button"
                          disabled={pendingKey === `rule-${rule.id}`}
                          onClick={() => toggleRuleEnabled(automater, rule)}
                        >
                          {rule.enabled ? "Deactivate" : "Activate"}
                        </button>
                        <button
                          className="button button--danger"
                          disabled={pendingKey === `rule-${rule.id}` || automater.rules.length === 1}
                          title={
                            automater.rules.length === 1
                              ? "Cannot delete an Automater's last rule — delete the Automater instead"
                              : undefined
                          }
                          onClick={() => {
                            if (!window.confirm(`Delete rule "${rule.name}"? This cannot be undone.`)) {
                              return;
                            }
                            withPending(`rule-${rule.id}`, () => deleteRule(automater.id, rule.id));
                          }}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
