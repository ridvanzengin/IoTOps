import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { createAutomater } from "../api/automater";
import { listCollectors } from "../api/collector";
import { listPlugins } from "../api/plugin";
import { listProjects } from "../api/project";
import { getTelemetrySchema } from "../api/telemetry";
import { isNumericType, SchemaConditionBuilder } from "../components/SchemaConditionBuilder";
import { defaultsFromSchema } from "../utils/jsonSchema";
import type {
  AutomaterInputPayload,
  ConditionPayload,
  RuleOperator,
  RuleSeverity,
} from "../types/automater";
import type { Collector, InputPluginPayload } from "../types/collector";
import type { Plugin } from "../types/plugin";
import type { Project } from "../types/project";
import type { TelemetryTableSchema } from "../types/telemetry";
import "./Collector.css";
import "./AutomaterEditor.css";
import "../components/SchemaConditionBuilder.css";

const RULE_SEVERITIES: RuleSeverity[] = ["low", "medium", "high", "critical"];

// Only one Celery action ships in v1.1 (structured logging) -- see
// iotops-workspace/ROADMAP.md's "already decided" list -- so the task name
// is fixed rather than asked of the user.
const CELERY_TASK_NAME = "automater.tasks.log_rule_match";

function extractPlaceholders(message: string): string[] {
  const matches = message.match(/\{([a-zA-Z0-9_]+)\}/g) ?? [];
  return matches.map((token) => token.slice(1, -1));
}

export function AutomaterEditor() {
  const navigate = useNavigate();
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [collectors, setCollectors] = useState<Collector[]>([]);
  const [schema, setSchema] = useState<TelemetryTableSchema[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const [ruleName, setRuleName] = useState("");
  const [category, setCategory] = useState("");
  const [eventType, setEventType] = useState("");
  const [severity, setSeverity] = useState<RuleSeverity>("low");
  const [message, setMessage] = useState("");
  const [ruleOperator, setRuleOperator] = useState<RuleOperator>("AND");
  const [identifiers, setIdentifiers] = useState<string[]>([]);
  const [ttl, setTtl] = useState("5m");

  const [table, setTable] = useState("");
  const [conditions, setConditions] = useState<ConditionPayload[]>([]);

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listPlugins()
      .then(setPlugins)
      .catch(() => setLoadError("Failed to load available plugins."));
    listProjects()
      .then(setProjects)
      .catch(() => setLoadError("Failed to load available projects."));
    listCollectors()
      .then(setCollectors)
      .catch(() => setLoadError("Failed to load collectors."));
    getTelemetrySchema()
      .then(setSchema)
      .catch(() => setLoadError("Failed to load table schema."));
  }, []);

  // No Input step: an Automater reuses whatever MQTT input the project's
  // own Collector already has configured, so it observes the same
  // telemetry stream the Collector writes to TimescaleDB. See
  // iotops-workspace/ROADMAP.md's Phase C redesign note.
  const derivedInput = useMemo((): InputPluginPayload | null => {
    const collector = collectors.find((c) => c.project_id === projectId);
    const mqttInput = collector?.inputs.find((input) => input.plugin_type === "mqtt");
    if (!mqttInput) return null;
    return {
      plugin_type: mqttInput.plugin_type,
      name: mqttInput.name,
      enabled: true,
      configuration: mqttInput.configuration,
    };
  }, [collectors, projectId]);

  const inputTagKeys = useMemo(
    () =>
      Array.isArray(derivedInput?.configuration?.tag_keys)
        ? (derivedInput.configuration.tag_keys as string[])
        : [],
    [derivedInput],
  );

  const missingTagKeys = useMemo(() => {
    const referenced = new Set([...identifiers, ...extractPlaceholders(message)]);
    const tableSchema = schema.find((t) => t.table === table);
    return [...referenced].filter((name) => {
      if (!name || inputTagKeys.includes(name)) return false;
      const column = tableSchema?.columns.find((c) => c.name === name);
      // Telegraf's JSON parser only silently drops *string*-valued fields
      // left out of tag_keys -- numeric fields don't need it. An
      // unresolvable name (not a real column) stays flagged since we can't
      // rule out it'll arrive as a string.
      return !column || !isNumericType(column.data_type);
    });
  }, [identifiers, message, inputTagKeys, schema, table]);

  const celeryPlugin = plugins.find((plugin) => plugin.name === "celery");

  function canSubmit(): boolean {
    return (
      name.trim().length > 0 &&
      projectId.length > 0 &&
      derivedInput !== null &&
      ruleName.trim().length > 0 &&
      table.length > 0 &&
      conditions.length > 0 &&
      celeryPlugin !== undefined
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    if (!derivedInput || !celeryPlugin) {
      setSubmitError("Missing required input or output plugin configuration.");
      return;
    }

    const payload: AutomaterInputPayload = {
      project_id: projectId,
      name,
      description,
      enabled: true,
      inputs: [derivedInput],
      rules: [
        {
          name: ruleName,
          description: "",
          category,
          event_type: eventType,
          severity,
          message,
          enabled: true,
          priority: 0,
          table,
          operator: ruleOperator,
          conditions,
          identifiers,
          ttl,
        },
      ],
      outputs: [
        {
          plugin_type: "celery",
          enabled: true,
          configuration: { ...defaultsFromSchema(celeryPlugin.configuration_schema), task_name: CELERY_TASK_NAME },
        },
      ],
    };

    setSubmitting(true);
    try {
      await createAutomater(payload);
      navigate("/automaters");
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Failed to create automater.");
    } finally {
      setSubmitting(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === projectId);
  const derivedCollector = collectors.find((c) => c.project_id === projectId);

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <h1>New Automater</h1>
      </div>
      <p style={{ margin: "-16px 0 24px", color: "var(--text)" }}>
        Pick the rule's metadata on the left, then build its condition(s) from the schema on the right.
        Input is reused from this project's Collector; output is always Celery.
      </p>

      {loadError && <p className="collector-page__error">{loadError}</p>}
      {submitError && <p className="collector-page__error">{submitError}</p>}

      <form onSubmit={handleSubmit}>
        <div className="automater-editor__grid">
          <div className="wizard-panel">
            <h2 className="wizard-panel__title">Basic Info</h2>
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

            {projectId && !derivedInput && (
              <p className="collector-page__error">
                No Collector with an MQTT input was found for {selectedProject?.name ?? "this project"}.
                Create one first — an Automater reuses the Collector's own input.
              </p>
            )}
            {derivedInput && derivedCollector && (
              <p className="automater-editor__warning" style={{ marginTop: -8 }}>
                Reusing input from Collector <strong>{derivedCollector.name}</strong>: topics{" "}
                {String((derivedInput.configuration.topics as string[] | undefined)?.join(", ") ?? "—")}, tag
                keys {inputTagKeys.length > 0 ? inputTagKeys.join(", ") : "none"}.
              </p>
            )}

            <label className="field">
              <span>Automater Name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label className="field">
              <span>Automater Description</span>
              <input value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>

            <h2 className="wizard-panel__title" style={{ marginTop: 24 }}>
              Rule
            </h2>
            <label className="field">
              <span>Rule Name</span>
              <input value={ruleName} onChange={(event) => setRuleName(event.target.value)} required />
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
              <span>Dedup Identifiers</span>
              <input
                value={identifiers.join(", ")}
                placeholder="device_id, node"
                onChange={(event) =>
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
              <span>Dedup TTL</span>
              <input value={ttl} placeholder="5m" onChange={(event) => setTtl(event.target.value)} />
            </label>
            <label className="field">
              <span>Message</span>
              <textarea rows={3} value={message} onChange={(event) => setMessage(event.target.value)} />
            </label>
            {missingTagKeys.length > 0 && (
              <p className="automater-editor__warning">
                ⚠ {missingTagKeys.join(", ")} {missingTagKeys.length === 1 ? "is" : "are"} referenced by
                identifiers or the message, but not in the reused input's Tag Keys. Telegraf silently drops
                any string field not listed there — add {missingTagKeys.length === 1 ? "it" : "them"} to the
                Collector's MQTT input Tag Keys, or this rule's dedup/message won't behave as expected.
              </p>
            )}
          </div>

          <div className="wizard-panel">
            <h2 className="wizard-panel__title">DB Schema</h2>
            <p className="wizard-panel__hint">
              Check the column(s) this rule evaluates. Every checked column comes from the same table —
              checking a column on a different table replaces the current selection.
            </p>
            <label className="field" style={{ maxWidth: 160 }}>
              <span>Combine with</span>
              <select value={ruleOperator} onChange={(event) => setRuleOperator(event.target.value as RuleOperator)}>
                <option value="AND">AND</option>
                <option value="OR">OR</option>
              </select>
            </label>
            <SchemaConditionBuilder
              schema={schema}
              table={table}
              conditions={conditions}
              onChange={(nextTable, nextConditions) => {
                setTable(nextTable);
                setConditions(nextConditions);
              }}
            />
          </div>
        </div>

        <div className="wizard-actions">
          <button type="button" className="button" onClick={() => navigate("/automaters")}>
            Cancel
          </button>
          <button type="submit" className="button button--primary" disabled={!canSubmit() || submitting}>
            {submitting ? "Creating..." : "Create Automater"}
          </button>
        </div>
      </form>
    </main>
  );
}
