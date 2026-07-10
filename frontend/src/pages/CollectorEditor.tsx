import { Fragment, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { createCollector } from "../api/collector";
import { listPlugins } from "../api/plugin";
import { listProjects } from "../api/project";
import { PluginRows } from "../components/PluginRows";
import { defaultsFromSchema } from "../utils/jsonSchema";
import type {
  CollectorInputPayload,
  InputPluginPayload,
  OutputPluginPayload,
  ProcessorPluginPayload,
} from "../types/collector";
import type { Plugin } from "../types/plugin";
import type { Project } from "../types/project";
import "./Collector.css";

const STEP_LABELS = ["Basic Info", "Input", "Output", "Review"];

// A Collector only ever writes to TimescaleDB -- "celery" is also
// registered under PluginCategory.OUTPUT (for Automater), but the celery
// output plugin enqueues every metric it receives unconditionally (see
// custom-telegraf/plugins/outputs/celery); it's only safe to use behind a
// rule processor that already filtered down to matched events. A Collector
// pipeline has no rule processor, so offering "celery" here would let a
// user flood the Celery queue with every raw telemetry point. See
// AutomaterEditor.tsx for the mirror image.
const COLLECTOR_OUTPUT_PLUGIN_NAMES = ["timescaledb"];

function StepIndicator({ currentStep }: { currentStep: number }) {
  return (
    <div className="wizard-steps">
      {STEP_LABELS.map((label, index) => {
        const step = index + 1;
        const state = step === currentStep ? "active" : step < currentStep ? "done" : "";
        return (
          <Fragment key={label}>
            {index > 0 && <div className="wizard-step-connector" />}
            <div className={`wizard-step ${state ? `wizard-step--${state}` : ""}`}>
              <span className="wizard-step__index">{step < currentStep ? "✓" : step}</span>
              {label}
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}

export function CollectorEditor() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [projectId, setProjectId] = useState("");
  const [inputs, setInputs] = useState<InputPluginPayload[]>([]);
  const [processors] = useState<ProcessorPluginPayload[]>([]);
  const [outputs, setOutputs] = useState<OutputPluginPayload[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listPlugins()
      .then(setPlugins)
      .catch(() => setError("Failed to load available plugins."));
    listProjects()
      .then(setProjects)
      .catch(() => setError("Failed to load available projects."));
  }, []);

  function canAdvance(): boolean {
    if (step === 1) return name.trim().length > 0 && projectId.length > 0;
    if (step === 2) return inputs.length > 0;
    if (step === 3) return outputs.length > 0;
    return true;
  }

  // Preload a default row the moment a step first becomes reachable, in the
  // same state update that advances the step, so the form arrives already
  // filled in rather than flashing empty before the defaults land.
  function goNext() {
    setError(null);
    if (!canAdvance()) {
      setError(stepErrorMessage(step));
      return;
    }
    const nextStep = Math.min(step + 1, STEP_LABELS.length);

    if (nextStep === 2 && inputs.length === 0) {
      const firstInput = plugins.find((plugin) => plugin.category === "input");
      if (firstInput) {
        setInputs([
          {
            plugin_type: firstInput.name,
            name: firstInput.name,
            enabled: true,
            configuration: defaultsFromSchema(firstInput.configuration_schema),
          },
        ]);
      }
    }
    if (nextStep === 3 && outputs.length === 0) {
      const firstOutput = plugins.find(
        (plugin) => plugin.category === "output" && COLLECTOR_OUTPUT_PLUGIN_NAMES.includes(plugin.name),
      );
      if (firstOutput) {
        setOutputs([
          {
            plugin_type: firstOutput.name,
            enabled: true,
            configuration: defaultsFromSchema(firstOutput.configuration_schema),
          },
        ]);
      }
    }

    setStep(nextStep);
  }

  function goBack() {
    setError(null);
    setStep((s) => Math.max(s - 1, 1));
  }

  function stepErrorMessage(currentStep: number): string {
    if (currentStep === 1) return "Give the collector a name and select a project to continue.";
    if (currentStep === 2) return "Add at least one input.";
    return "Add at least one output.";
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const payload: CollectorInputPayload = {
      project_id: projectId,
      name,
      description,
      enabled: true,
      inputs,
      processors,
      outputs,
    };

    setSubmitting(true);
    try {
      await createCollector(payload);
      navigate("/collectors");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create collector.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="collector-page collector-page--form">
      <h1>New Collector</h1>
      <p style={{ margin: "8px 0 24px", color: "var(--text)" }}>
        Configure telemetry inputs and outputs, then deploy.
      </p>

      <StepIndicator currentStep={step} />

      {error && <p className="collector-page__error">{error}</p>}

      <form className="wizard-panel" onSubmit={handleSubmit}>
        {step === 1 && (
          <div>
            <h2 className="wizard-panel__title">Basic Info</h2>
            <p className="wizard-panel__hint">Name and describe this collector.</p>
            <label className="field">
              <span>Name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} required autoFocus />
            </label>
            <label className="field">
              <span>Description</span>
              <input value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
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
            {projects.length === 0 && (
              <p className="collector-page__error" style={{ marginTop: 12 }}>
                No projects exist yet. Create one first.
              </p>
            )}
          </div>
        )}

        {step === 2 && (
          <div>
            <h2 className="wizard-panel__title">Input</h2>
            <p className="wizard-panel__hint">
              Where telemetry comes from. Fields are preloaded with sensible defaults for this stack.
            </p>
            <PluginRows
              category="input"
              availablePlugins={plugins}
              rows={inputs}
              onChange={setInputs}
              makeRow={(plugin) => ({
                plugin_type: plugin.name,
                name: plugin.name,
                enabled: true,
                configuration: defaultsFromSchema(plugin.configuration_schema),
              })}
              renderExtraFields={(row, update) => (
                <input
                  className="plugin-row__name-field"
                  value={row.name}
                  placeholder="instance name"
                  onChange={(event) => update({ name: event.target.value })}
                />
              )}
            />
          </div>
        )}

        {step === 3 && (
          <div>
            <h2 className="wizard-panel__title">Output</h2>
            <p className="wizard-panel__hint">Where telemetry is written to.</p>
            <PluginRows
              category="output"
              availablePlugins={plugins.filter((plugin) => COLLECTOR_OUTPUT_PLUGIN_NAMES.includes(plugin.name))}
              rows={outputs}
              onChange={setOutputs}
              makeRow={(plugin) => ({
                plugin_type: plugin.name,
                enabled: true,
                configuration: defaultsFromSchema(plugin.configuration_schema),
              })}
            />
          </div>
        )}

        {step === 4 && (
          <div>
            <h2 className="wizard-panel__title">Review</h2>
            <p className="wizard-panel__hint">Confirm before creating the collector.</p>
            <div className="wizard-review">
              <div className="wizard-review__section">
                <div className="wizard-review__label">Name</div>
                <div>{name}</div>
                {description && <div style={{ marginTop: 4 }}>{description}</div>}
              </div>
              <div className="wizard-review__section">
                <div className="wizard-review__label">Project</div>
                <div>{projects.find((project) => project.id === projectId)?.name ?? "—"}</div>
              </div>
              <div className="wizard-review__section">
                <div className="wizard-review__label">Inputs</div>
                {inputs.map((input, i) => (
                  <div key={i}>
                    {input.name} ({input.plugin_type}){input.enabled ? "" : " — disabled"}
                  </div>
                ))}
              </div>
              <div className="wizard-review__section">
                <div className="wizard-review__label">Outputs</div>
                {outputs.map((output, i) => (
                  <div key={i}>
                    {output.plugin_type}
                    {output.enabled ? "" : " — disabled"}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="wizard-actions">
          <button type="button" className="button" onClick={goBack} disabled={step === 1}>
            Back
          </button>
          {step < STEP_LABELS.length ? (
            <button key="next" type="button" className="button button--primary" onClick={goNext}>
              Next
            </button>
          ) : (
            <button key="submit" type="submit" className="button button--primary" disabled={submitting}>
              {submitting ? "Creating..." : "Create Collector"}
            </button>
          )}
        </div>
      </form>
    </main>
  );
}
