import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { createRule, listAutomaters } from "../api/automater";
import { listCollectors } from "../api/collector";
import { listPlugins } from "../api/plugin";
import { listProjects } from "../api/project";
import { getTelemetrySchema } from "../api/telemetry";
import { isNumericType, SchemaConditionBuilder } from "../components/SchemaConditionBuilder";
import type {
  Automater,
  ConditionPayload,
  CreateRuleRequest,
  ResolveMode,
  RulePayload,
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
const RESOLVE_MODES: ResolveMode[] = ["auto", "manual"];

// A dropdown option value, not a real Automater id -- selects the "create a
// new Automater alongside this rule" path instead of attaching to an
// existing one. See ROADMAP.md's Automater/Rule redesign note: a project
// can have more than one Automater (mirrors Collector, which was never
// restricted to one per project either), so the user picks which one a new
// rule joins rather than it being implicit.
const NEW_AUTOMATER = "__new__";

function extractPlaceholders(message: string): string[] {
  const matches = message.match(/\{([a-zA-Z0-9_]+)\}/g) ?? [];
  return matches.map((token) => token.slice(1, -1));
}

// Best-effort, informational only -- different input plugin types name
// their "where does this come from" field differently (mqtt/kafka:
// topics, http: paths, amqp: queue). Falls back to nothing rather than
// guessing at a field that doesn't exist for this plugin_type.
function describeInputSource(configuration: Record<string, unknown>): string | null {
  for (const key of ["topics", "paths", "queue"]) {
    const value = configuration[key];
    if (Array.isArray(value) && value.length > 0) return value.join(", ");
    if (typeof value === "string" && value) return value;
  }
  return null;
}

export function AutomaterEditor() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [collectors, setCollectors] = useState<Collector[]>([]);
  const [automaters, setAutomaters] = useState<Automater[]>([]);
  const [schema, setSchema] = useState<TelemetryTableSchema[]>([]);
  const [inputPlugins, setInputPlugins] = useState<Plugin[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [projectId, setProjectId] = useState("");
  const [automaterId, setAutomaterId] = useState("");
  const [automaterName, setAutomaterName] = useState("");
  const [automaterDescription, setAutomaterDescription] = useState("");
  const [collectorId, setCollectorId] = useState("");

  const [ruleName, setRuleName] = useState("");
  const [category, setCategory] = useState("");
  const [eventType, setEventType] = useState("");
  const [severity, setSeverity] = useState<RuleSeverity>("low");
  const [message, setMessage] = useState("");
  const [identifiers, setIdentifiers] = useState<string[]>([]);
  const [ttl, setTtl] = useState("5m");
  const [resolveMode, setResolveMode] = useState<ResolveMode>("auto");

  const [table, setTable] = useState("");
  const [conditions, setConditions] = useState<ConditionPayload[]>([]);

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setLoadError("Failed to load available projects."));
    listCollectors()
      .then(setCollectors)
      .catch(() => setLoadError("Failed to load collectors."));
    listAutomaters()
      .then(setAutomaters)
      .catch(() => setLoadError("Failed to load automaters."));
    getTelemetrySchema()
      .then(setSchema)
      .catch(() => setLoadError("Failed to load table schema."));
    listPlugins("input")
      .then(setInputPlugins)
      .catch(() => setLoadError("Failed to load input plugin types."));
  }, []);

  // Telegraf measurement-names an input after its own plugin's Telegraf
  // name (e.g. "mqtt_consumer", "kafka_consumer") when name_override isn't
  // set on that instance -- this map lets input-derivation logic match
  // that real fallback for *any* input plugin_type, not just mqtt. See
  // iotops-workspace/ROADMAP.md's data-sources note.
  const telegrafNameByPluginType = useMemo(
    () => new Map(inputPlugins.map((plugin) => [plugin.name, plugin.telegraf_name])),
    [inputPlugins],
  );

  const projectAutomaters = useMemo(
    () => automaters.filter((a) => a.project_id === projectId),
    [automaters, projectId],
  );
  const projectCollectors = useMemo(
    () => collectors.filter((c) => c.project_id === projectId),
    [collectors, projectId],
  );

  const inputTableNames = useCallback(
    (inputs: { plugin_type: string; configuration: Record<string, unknown> }[]): Set<string> => {
      const names = new Set<string>();
      for (const input of inputs) {
        const override = input.configuration?.name_override;
        // Telegraf measurement-names an input after its own plugin's
        // Telegraf name (e.g. "mqtt_consumer", "kafka_consumer") when
        // name_override isn't set -- match that per-plugin-type default
        // rather than treating "no override" as "no table", or the input
        // just silently vanishes from this filtered list.
        const fallback = telegrafNameByPluginType.get(input.plugin_type) ?? input.plugin_type;
        names.add(typeof override === "string" && override ? override : fallback);
      }
      return names;
    },
    [telegrafNameByPluginType],
  );

  // Every table any of the project's Collectors actually write to, across
  // any input plugin type (mqtt, kafka, http, amqp, ...) -- narrows the DB
  // Schema panel down from "every table in TimescaleDB, from every
  // project" (confusing once more than one project/showcase exists) to
  // just the ones relevant here. Further narrowed to a single Collector's
  // own tables below once one is picked.
  const projectTables = useMemo(
    () => inputTableNames(projectCollectors.flatMap((c) => c.inputs)),
    [projectCollectors, inputTableNames],
  );
  const collectorTables = useMemo(() => {
    const collector = collectors.find((c) => c.id === collectorId);
    return collector ? inputTableNames(collector.inputs) : null;
  }, [collectors, collectorId, inputTableNames]);

  const visibleSchema = useMemo(() => {
    if (!projectId) return schema;
    const allowed = collectorTables ?? projectTables;
    return schema.filter((t) => allowed.has(t.table));
  }, [schema, projectId, projectTables, collectorTables]);

  function handleProjectChange(nextProjectId: string) {
    setProjectId(nextProjectId);
    setAutomaterId("");
    setAutomaterName("");
    setAutomaterDescription("");
    setCollectorId("");
    // The previously chosen table/conditions may not belong to the new
    // project at all -- clear them rather than leave a selection that's
    // now hidden by the filter above but still technically submitted.
    setTable("");
    setConditions([]);
  }

  const isNewAutomater = automaterId === NEW_AUTOMATER;

  // An Automater can watch more than one table (mirrors how a Collector can
  // already have more than one input) -- so an *existing* Automater
  // doesn't necessarily already have an input for whatever table this new
  // rule ends up targeting. This is the set of tables it already covers,
  // across any input plugin type, so we can tell "reuse an existing input"
  // apart from "needs a new one".
  const existingAutomaterTables = useMemo(() => {
    if (isNewAutomater || !automaterId) return new Set<string>();
    const automater = automaters.find((a) => a.id === automaterId);
    return new Set(
      (automater?.inputs ?? [])
        .map((i) => i.configuration?.name_override as string | undefined)
        .filter((name): name is string => Boolean(name)),
    );
  }, [isNewAutomater, automaterId, automaters]);

  // True once a table's been chosen and the selected existing Automater
  // doesn't already have an input for it -- at that point we need a
  // Collector picker (same as the new-Automater path) to derive one from,
  // same as create_rule requires server-side.
  const needsNewInputForTable = !isNewAutomater && automaterId.length > 0 && table.length > 0 && !existingAutomaterTables.has(table);

  // No Input step for an existing Automater whose input already covers this
  // rule's table -- it's just reused. Otherwise (a brand new Automater, or
  // an existing one that doesn't cover this table yet) the input is derived
  // from whichever Collector the user picks below -- not re-asked field by
  // field, since it must observe the same telemetry stream that Collector
  // already writes to TimescaleDB anyway. See ROADMAP.md's Phase C /
  // Automater-Rule notes.
  const derivedInput = useMemo((): InputPluginPayload | null => {
    if (!isNewAutomater && automaterId && !needsNewInputForTable) {
      const matchedInput = automaters
        .find((a) => a.id === automaterId)
        ?.inputs.find((i) => i.configuration?.name_override === table);
      if (!matchedInput) return null;
      return {
        plugin_type: matchedInput.plugin_type,
        name: matchedInput.name,
        enabled: true,
        configuration: matchedInput.configuration,
      };
    }

    // A Collector can have more than one input (one per table/topic -- e.g.
    // device_metrics and device_status, possibly fed by different plugin
    // types), so a multi-input Collector's input must be matched to the
    // rule's target table via name_override. But `table` isn't chosen
    // until the user interacts with the DB Schema panel -- for the common
    // case of a single-input Collector there's no ambiguity to resolve in
    // the first place, so don't make that one wait on `table` too (it used
    // to resolve immediately on Collector selection; only gate on `table`
    // when there's actually more than one candidate to disambiguate).
    const candidates = collectors.find((c) => c.id === collectorId)?.inputs ?? [];
    const matchedInput =
      candidates.length === 1 ? candidates[0] : candidates.find((i) => i.configuration?.name_override === table);
    if (!matchedInput) return null;
    return {
      plugin_type: matchedInput.plugin_type,
      name: matchedInput.name,
      enabled: true,
      configuration: matchedInput.configuration,
    };
  }, [isNewAutomater, automaterId, needsNewInputForTable, automaters, collectors, collectorId, table]);

  // Distinguishes "this Collector genuinely has no input" from "it has more
  // than one and we can't tell which until a table is picked" -- these need
  // different error messages (see the Collector-picker JSX below).
  const collectorInputCount = useMemo(
    () => collectors.find((c) => c.id === collectorId)?.inputs.length ?? 0,
    [collectors, collectorId],
  );

  const inputTagKeys = useMemo(
    () =>
      Array.isArray(derivedInput?.configuration?.tag_keys)
        ? (derivedInput.configuration.tag_keys as string[])
        : [],
    [derivedInput],
  );

  // Tag keys are the natural default for "which fields identify one
  // occurrence" -- pre-fill Dedup Identifiers with them whenever the
  // resolved input changes (a different Automater or Collector picked).
  // Re-fires only when inputTagKeys itself changes, so it won't clobber a
  // manual edit made after settling on an input.
  useEffect(() => {
    if (inputTagKeys.length > 0) {
      setIdentifiers(inputTagKeys);
    }
  }, [inputTagKeys]);

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

  function canSubmit(): boolean {
    const automaterPartValid = isNewAutomater
      ? automaterName.trim().length > 0 && collectorId.length > 0
      : automaterId.length > 0 && (!needsNewInputForTable || collectorId.length > 0);
    return (
      projectId.length > 0 &&
      automaterPartValid &&
      ruleName.trim().length > 0 &&
      table.length > 0 &&
      conditions.length > 0
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    const rule: RulePayload = {
      name: ruleName,
      description: "",
      category,
      event_type: eventType,
      severity,
      message,
      enabled: true,
      priority: 0,
      resolve_mode: resolveMode,
      table,
      conditions,
      identifiers,
      ttl,
    };

    const payload: CreateRuleRequest = {
      project_id: projectId,
      rule,
      automater_id: isNewAutomater ? null : automaterId,
      automater_name: isNewAutomater ? automaterName : null,
      automater_description: isNewAutomater ? automaterDescription : "",
      // Needed both for a brand new Automater and for an existing one that
      // doesn't have an input for this rule's table yet -- unneeded (and
      // omitted) when reusing an existing Automater's already-covered table.
      collector_id: isNewAutomater || needsNewInputForTable ? collectorId : null,
    };

    setSubmitting(true);
    try {
      await createRule(payload);
      navigate("/automaters");
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Failed to create rule.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="collector-page">
      <div className="collector-page__header">
        <h1>New Real-time Rule</h1>
      </div>
      <p style={{ margin: "-16px 0 24px", color: "var(--text)" }}>
        Pick the rule's metadata on the left, then build its condition(s) from the schema on the right.
        Attach it to an existing Automater or create a new one.
      </p>

      {loadError && <p className="collector-page__error">{loadError}</p>}
      {submitError && <p className="collector-page__error">{submitError}</p>}

      <form onSubmit={handleSubmit}>
        <div className="automater-editor__grid">
          <div className="wizard-panel">
            <h2 className="wizard-panel__title">Where this rule lives</h2>
            <label className="field">
              <span>Project</span>
              <select
                value={projectId}
                onChange={(event) => handleProjectChange(event.target.value)}
                required
              >
                <option value="">Select a project</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Automater</span>
              <select
                value={automaterId}
                onChange={(event) => setAutomaterId(event.target.value)}
                required
                disabled={!projectId}
              >
                <option value="">Select an automater</option>
                {projectAutomaters.map((automater) => (
                  <option key={automater.id} value={automater.id}>
                    {automater.name}
                  </option>
                ))}
                <option value={NEW_AUTOMATER}>+ New Automater</option>
              </select>
            </label>

            {isNewAutomater && (
              <>
                <label className="field">
                  <span>New Automater Name</span>
                  <input
                    value={automaterName}
                    onChange={(event) => setAutomaterName(event.target.value)}
                    required
                  />
                </label>
                <label className="field">
                  <span>New Automater Description</span>
                  <input
                    value={automaterDescription}
                    onChange={(event) => setAutomaterDescription(event.target.value)}
                  />
                </label>
              </>
            )}

            {!isNewAutomater && automaterId && existingAutomaterTables.size > 0 && (
              <p className="automater-editor__warning" style={{ marginTop: -8 }}>
                This Automater already watches: {[...existingAutomaterTables].join(", ")}. Picking a
                different table on the right will add a new input to it.
              </p>
            )}

            {(isNewAutomater || needsNewInputForTable) && (
              <>
                <label className="field">
                  <span>Collector{needsNewInputForTable ? ` for ${table}` : ""}</span>
                  <select
                    value={collectorId}
                    onChange={(event) => setCollectorId(event.target.value)}
                    required
                  >
                    <option value="">Select a collector</option>
                    {projectCollectors.map((collector) => (
                      <option key={collector.id} value={collector.id}>
                        {collector.name}
                      </option>
                    ))}
                  </select>
                </label>
                {projectId && projectCollectors.length === 0 && (
                  <p className="collector-page__error">
                    No Collector exists for this project yet — create one first, an Automater reuses one
                    of a Collector's own inputs.
                  </p>
                )}
                {collectorId && !derivedInput && collectorInputCount === 0 && (
                  <p className="collector-page__error">
                    The selected Collector has no input configured.
                  </p>
                )}
                {collectorId && !derivedInput && collectorInputCount > 1 && (
                  <p className="automater-editor__warning" style={{ marginTop: -8 }}>
                    This Collector has {collectorInputCount} inputs — pick a column from a table in
                    the DB Schema panel first, so we know which one this rule's table is.
                  </p>
                )}
              </>
            )}
            {derivedInput && (
              <p className="automater-editor__warning" style={{ marginTop: -8 }}>
                {describeInputSource(derivedInput.configuration) &&
                  `Input source ${describeInputSource(derivedInput.configuration)}, `}
                tag keys {inputTagKeys.length > 0 ? inputTagKeys.join(", ") : "none"}.
              </p>
            )}

            <h2 className="wizard-panel__title" style={{ marginTop: 24 }}>
              Rule
            </h2>
            <div className="automater-editor__field-grid">
              <label className="field">
                <span>Rule Name</span>
                <input value={ruleName} onChange={(event) => setRuleName(event.target.value)} required />
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
                <span>Identifiers</span>
                <input
                  key={identifiers.join(",")}
                  defaultValue={identifiers.join(", ")}
                  placeholder="device_id, node"
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
                <span>Dedup TTL</span>
                <input value={ttl} placeholder="5m" onChange={(event) => setTtl(event.target.value)} />
              </label>
              <label className="field">
                <span>Resolution</span>
                <select
                  value={resolveMode}
                  onChange={(event) => setResolveMode(event.target.value as ResolveMode)}
                >
                  {RESOLVE_MODES.map((mode) => (
                    <option key={mode} value={mode}>
                      {mode === "auto" ? "Auto-resolve" : "Manual-resolve"}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {resolveMode === "manual" && (
              <p className="automater-editor__warning" style={{ marginTop: -8 }}>
                This rule will never auto-clear -- a matching occurrence stays active until someone
                resolves it from the Events sidebar.
              </p>
            )}
            <label className="field">
              <span>Message</span>
              <textarea rows={3} value={message} onChange={(event) => setMessage(event.target.value)} />
            </label>
            {missingTagKeys.length > 0 && (
              <p className="automater-editor__warning">
                ⚠ {missingTagKeys.join(", ")} {missingTagKeys.length === 1 ? "is" : "are"} referenced by
                identifiers or the message, but not in the reused input's Tag Keys. Telegraf silently drops
                any string field not listed there — add {missingTagKeys.length === 1 ? "it" : "them"} to the
                Collector's input Tag Keys, or this rule's dedup/message won't behave as expected.
              </p>
            )}

            <div className="wizard-actions">
              <button type="button" className="button" onClick={() => navigate("/automaters")}>
                Cancel
              </button>
              <button type="submit" className="button button--primary" disabled={!canSubmit() || submitting}>
                {submitting ? "Creating..." : "Create Rule"}
              </button>
            </div>
          </div>

          <div className="wizard-panel">
            <h2 className="wizard-panel__title">DB Schema</h2>
            <SchemaConditionBuilder
              schema={visibleSchema}
              table={table}
              conditions={conditions}
              onChange={(nextTable, nextConditions) => {
                setTable(nextTable);
                setConditions(nextConditions);
              }}
            />
          </div>
        </div>
      </form>
    </main>
  );
}
