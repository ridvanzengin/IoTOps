# Development Plan

Version: 0.2.0 (Phased Roadmap)

## Goal

Build a self-hosted, domain-agnostic IoT platform. Ship a working core
telemetry pipeline as v1, demonstrated end-to-end through a Beekeeping
showcase, then add automation, AI, and further domain showcases as fast
follow-up releases.

IoTOps is a generic platform. Beekeeping is only the first showcase — see
[Future — Additional Domain Showcases](#future--additional-domain-showcases).

---

# Release Phases

| Phase | Contents | Goal |
|-------|----------|------|
| **v1** | Milestones 0–4 | Ship / announce target — full Collector → Telemetry → Dashboard pipeline |
| **v1.1** | Milestone 5 | Automation Engine (rule-based event detection) |
| **v1.2** | Milestone 6 | AI Assistant (natural-language SQL generation) |
| **Future** | New showcases | Additional domain demos proving the platform is not beekeeping-specific |

No feature below is cancelled. Automation and AI are deferred, not dropped —
the goal is to get a working, demoable platform shipped and announced
faster, then keep shipping.

---

# v1 — Core Telemetry Platform (Ship Target)

## Milestone 0 — Repository Bootstrap

### Objective

Create the project skeleton.

### Tasks

- Create backend FastAPI project.
- Create frontend React + TypeScript + Vite project.
- Add Docker Compose.
- Add MongoDB.
- Add TimescaleDB.
- Add Mosquitto MQTT.
- Add Redis.
- Configure environment variables.
- Add health endpoints.

**Status: done.**

**Acceptance Criteria**

- `docker compose up` starts all services.
- `/health` returns OK.
- Frontend loads.

---

## Milestone 1 — Collector Management

### Objective

Create and deploy collectors.

### Tasks

- Implement Pydantic models.
- Implement Mongo repositories.
- Implement plugin registry.
- Implement MQTT Input plugin.
- Implement Timescale Output plugin.
- Implement TOML generator.
- Implement Docker lifecycle.
- Implement Collector CRUD API.
- Implement Collector UI.

**Status: done.** As built:

- Plugin registry pairs a `PluginDefinition` (metadata) with a typed
  Pydantic config model per plugin, under `plugin/inputs/` and
  `plugin/outputs/`; every config model inherits a shared `CommonOpts`
  mixin. See [domain-models.md](domain-models.md#plugin-configuration-models)
  and [repository-structure.md](repository-structure.md#plugin-module).
- Collector UI is a 4-step wizard (Basic Info → Input → Output → Review)
  with a schema-driven config form that preloads real defaults and
  collapses advanced fields behind a disclosure — no per-plugin
  hardcoded forms.
- Docker lifecycle uses docker-outside-of-docker (backend gets the host
  `docker.sock` plus a bind-mounted `runtime/` dir) to manage sibling
  Telegraf containers; see `docker-compose.yml`.

**Acceptance Criteria**

- User can create a Collector.
- Collector launches as Docker container.
- Container status is visible.

---

## Milestone 2 — Telemetry Pipeline

### Objective

Receive MQTT data and store it.

### Tasks

- Create Timescale schema.
- Configure Telegraf outputs.
- Add MQTT test publisher.
- Verify ingestion.
- Create telemetry query API.

**Status: done.** As built:

- No separate schema-migration step: the TimescaleDB output plugin's
  `create_templates` default was changed to both `CREATE TABLE` and
  `SELECT create_hypertable(...)`, so every table a Collector creates is
  a proper hypertable automatically, with no manual DB setup.
- Correct Telegraf output config had to be verified against a real
  `telegraf:1.32-alpine` container, not just reasoned about — several
  assumptions inherited from a reference config turned out to be wrong
  for this Telegraf version (`inherit_tags`/`plugin_tags` aren't real
  options; `outputs.postgresql` has no `table` setting, since table name
  comes from the metric's measurement name / a `name_override` on the
  input; an empty `create_templates` list disables auto-creation rather
  than falling back to Telegraf's built-in template). Telegraf's JSON
  parser also silently drops string-valued fields unless they're listed
  in `json_string_fields` — a real data-loss footgun now modeled
  explicitly rather than discovered by a user.
- MQTT test publisher lives at `examples/mqtt-publisher/`, off by
  default (`docker compose --profile tools up mqtt-publisher`) — see
  [repository-structure.md](repository-structure.md#examples-directory).
- Telemetry query API is a new `telemetry/` backend module (not a
  Mongo-backed domain module like the others — see
  [repository-structure.md](repository-structure.md#telemetry-module)):
  `GET /api/telemetry/tables` and `GET /api/telemetry/{table}`, backed by
  `asyncpg` directly against TimescaleDB.

**Acceptance Criteria**

- Publishing MQTT messages stores rows in TimescaleDB.
- API can query recent telemetry.

---

## Milestone 3 — Dashboard System

### Objective

Visualize telemetry.

### Tasks

- Implement a new Project root entity (grouping a Collector with its
  Automaters and Dashboards) and retrofit Collector with a required
  `project_id`.
- Implement Dashboard models (including `project_id`).
- Implement Panel models.
- Implement chart models.
- Create dashboard CRUD API.
- Build dashboard editor UI.
- Integrate Apache ECharts.
- Add line, bar, scatter, pie, and gauge charts.
- Extend the telemetry module with a schema-introspection endpoint and a
  guarded arbitrary-SQL query endpoint, since Panels need more than
  recent-rows-from-one-table.

**Status: in progress.** A narrow slice of Milestone 6 (AI Assistant) was
pulled forward alongside this milestone: `POST /api/ai/sql`, backed by a
local Ollama model, is implemented now so the Panel builder can offer an
AI-only natural-language query builder — by design, no manual/visual query
builder was built at all; SQL is only ever produced by hand-editing the
generated statement or asking the AI again. SQL explanation and the other
AI endpoints remain deferred to the real Milestone 6.

**Follow-up work within this milestone, not done in the initial pass:**

- **Dual-axis / mixed-series-type panels** (e.g. temperature + humidity on
  the same panel with two y-axes, or a scatter series of discrete events
  overlaid on a temperature line chart). The current `Chart` discriminated
  union (`dashboard/models.py`) supports exactly one chart type with one
  series shape per panel — no multi-series-mixed-type or secondary-axis
  support. This needs a real model change (a new `Chart` variant or a
  restructured `series: list[SeriesConfig]` shape) before either manual or
  AI-suggested panels can express it. Track alongside the "Suggested
  Dashboards" work above, since a suggestion engine can't propose what the
  model can't represent — but the model change itself is independent and
  should land whenever Dashboard work resumes, not gated on the AI feature.
- Full Variable UI (Grafana-style dropdown template variables with
  predicate-based query substitution) — the `Variable` model already exists
  in `dashboard/models.py`, but the canvas currently only shows a
  placeholder "no variables" state, no create/edit UI or `$variable`
  substitution into panel queries.
- Dashboard-level time range picker actually filtering panel queries (the
  canvas header currently has the slot but it's not wired to re-run queries
  with a time bound).

**Acceptance Criteria**

- User can create a Project.
- User can create a dashboard scoped to a Project.
- User can add panels, generating their SQL via the AI query builder.
- Telemetry is rendered as charts.

---

## Milestone 4 — Beekeeping Showcase (v1 scope)

### Objective

Ship the first working, end-to-end demonstration of the platform. Beekeeping
is the first of several planned domain showcases — see
[Future — Additional Domain Showcases](#future--additional-domain-showcases).

### Tasks

- Create MQTT simulator.
- Simulate hive temperature.
- Simulate humidity.
- Simulate hive weight.
- Create default dashboard.

The swarm-alert rule is intentionally excluded from v1 — it depends on the
Automation Engine and ships in v1.1 instead.

**Acceptance Criteria**

- Demo runs with one command.
- Dashboard shows live hive metrics.

---

## v1 Definition of Done

IoTOps v1 is ready to ship and announce when a user can:

- Create an MQTT Collector from the UI.
- Deploy it as a Docker container.
- Ingest telemetry.
- Store telemetry in TimescaleDB.
- Build a dashboard.
- Visualize data.
- Run the Beekeeping showcase end-to-end with one command.

---

# v1.1 — Automation Engine

## Milestone 5 — Automation Engine

### Objective

Detect simple events.

### Tasks

- Implement Rule models.
- Implement Condition models.
- Build custom Telegraf Rule Processor plugin.
- Build custom Celery Output plugin.
- Create Automater CRUD API.
- Deploy Automater containers.
- Implement Celery worker.
- Add swarm-alert rule to the Beekeeping showcase.

**Acceptance Criteria**

- Rule `temperature > 30` triggers a Celery task.
- Event payload contains matching metric data.
- Beekeeping showcase demonstrates a live swarm-alert triggered by simulated
  conditions.

This milestone carries the highest schedule risk in the roadmap: the Rule
Processor and Celery Output plugins are custom Telegraf (Go) plugins, a
different toolchain from the rest of the stack. Keeping it out of v1 keeps
that risk off the critical path for the initial release.

---

# v1.2 — AI Assistant

## Milestone 6 — AI Assistant

### Objective

Generate SQL from natural language.

### Tasks

- Integrate Ollama.
- Add SQL generation endpoint.
- Add SQL explanation endpoint.
- Add frontend AI query builder.
- Validate generated SQL.

**Acceptance Criteria**

- User enters: "Show hive temperature for the last 24 hours."
- SQL is generated.
- Chart renders successfully.

---

# Future — Suggested Dashboards & Automations

Ship **after both Milestone 3 (Dashboard) and Milestone 5 (Automater) are
complete** — a "Suggest a dashboard" button pairs with a "Suggest an
automation" button, and both need their respective target module to exist
first.

### Tasks

- A model-selection dropdown in a new Settings/config nav area: lists the
  local Ollama model (default) plus any configured hosted models (e.g.
  Claude via the Anthropic API) as opt-in alternatives. Persists the user's
  choice; every "Suggest..." action uses whichever model is selected there.
- `POST /api/ai/dashboard`: given a project's telemetry schema, propose a
  starter set of panels (chart type, query, layout) as a reviewable draft —
  never auto-saved. See `docs/architecture.md`'s AI Integration section,
  which already anticipates this endpoint.
- `POST /api/ai/automation` (new, not yet documented anywhere): given a
  project's telemetry schema, propose starter Automater rules/conditions as
  a reviewable draft.
- Both endpoints share a provider abstraction (local Ollama vs. a hosted
  model like Claude) so the model-selection dropdown controls a real
  pluggable backend, not just Ollama.
- Self-correction loop: generated panel/rule queries and conditions should
  be validated (e.g. run through `/api/telemetry/query`) before being shown
  to the user, retrying once on failure rather than surfacing broken output.

---

# Future — Additional Domain Showcases

IoTOps is a generic IoT operations platform. Beekeeping was chosen as the
first showcase because it's small, visual, and easy to simulate — not
because the platform is beekeeping-specific.

Once v1.1/v1.2 are stable, additional showcases should be added to prove the
platform generalizes across domains. Candidates (from
[docs/vision.md](vision.md)):

- Industrial Monitoring
- Greenhouse Automation
- Weather Stations
- Smart Buildings
- Energy Monitoring
- Smart Home Systems

Each future showcase should reuse the existing Collector / Automater /
Dashboard primitives and ship as an installable template rather than
bespoke code, per the Extensibility principle in the vision doc.

---

# Internal Pipeline Abstraction

Although the UI exposes **Collector** and **Automater**, the backend should internally use a shared **Pipeline** model.

**Not yet factored out.** `collector/models.py` currently has
`CollectorPluginsBase` (inputs/processors/outputs + the "at least one
input and one output" validation) playing this role directly on
`Collector`, rather than a separate reusable `Pipeline` class. This was
fine with only Collector implemented; when Automater (Milestone 5) is
built, extract a real `Pipeline` base at that point rather than
duplicating the inputs/processors/outputs plumbing.

## Internal Structure

### Pipeline

- inputs[]
- processors[]
- outputs[]

### Collector

- Pipeline
- MQTT Input
- Timescale Output

### Automater

- Pipeline
- MQTT Input
- Rule Processor
- Celery Output

---

# What NOT To Build Yet

- Multi-user support
- RBAC
- Kubernetes
- Window-based analytics
- Machine learning
- Remote agents
- Template marketplace
- Visual rule builder
- Complex event processing
- Real-time streaming dashboards

---

# Recommended Build Order

1. Repository + Docker
2. Collector CRUD
3. MQTT → TimescaleDB
4. Basic Dashboard
5. Beekeeping Demo — **ship v1 here**
6. Automater — v1.1
7. AI SQL — v1.2
8. Additional domain showcases — future

---

# Full Platform Definition of Done

The complete IoTOps vision (v1.2 and beyond) is done when a user can:

- Create an MQTT Collector from the UI.
- Deploy it as a Docker container.
- Ingest telemetry.
- Store telemetry in TimescaleDB.
- Create an Automater rule.
- Trigger a Celery task.
- Build a dashboard.
- Visualize data.
- Generate SQL using the local LLM.
- Run the complete Beekeeping showcase.

This is the long-term target, not the v1 ship bar — see
[v1 Definition of Done](#v1-definition-of-done) for what actually gates the
first release.

---

# Recommendation

Start with **Milestone 0** and **Milestone 1** only.

First validate:

**MQTT → Collector → TimescaleDB**

with Docker lifecycle management.

Once that pipeline works, continue through the rest of v1 (Dashboard,
Beekeeping showcase) and ship/announce. Automation, AI, and additional
domain showcases follow as v1.1, v1.2, and beyond — they are fast-follow
releases, not blockers for the initial launch.
