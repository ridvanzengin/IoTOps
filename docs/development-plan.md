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
- A second, more serious template bug was found the same way while
  end-to-end testing Milestone 3's Variable feature against a real
  Collector: `TimescaleDBOutputConfig.add_column_templates` /
  `tag_table_add_column_templates` used `{{.column}}`, a template
  variable that doesn't exist in this plugin's context (the real one is
  `.columns`, a list needing a `join` filter) — this silently broke
  schema evolution for every Collector, permanently dropping any field
  that arrived after a table's initial `CREATE TABLE` instead of adding
  its column. Fixed at the model-default level (so it's not just a
  per-Collector data fix) — see the comment on
  `TimescaleDBOutputConfig.add_column_templates` in
  `backend/app/plugin/outputs/timescaledb.py`.
- Two more real-world gotchas surfaced setting up a Collector with two
  MQTT inputs (one per topic, per `examples/mqtt-publisher/README.md`'s
  documented pattern): (1) `name_override` — not `topics` or having two
  separate input blocks — is what actually splits inputs into separate
  tables; Telegraf's `mqtt_consumer` plugin defaults every instance's
  measurement name to its own plugin name regardless of topic, so two
  inputs with no `name_override` silently merge into one table. (2) A
  JSON string field doesn't strictly need `json_string_fields` — listing
  it in `tag_keys` instead (promoting it to an InfluxDB-style tag) works
  too and is arguably the more correct modeling choice for an
  identifying/filtering field like `device_id` (tags are Telegraf's
  built-in "this is metadata, not a measurement" concept), since tag
  extraction doesn't do the numeric-vs-string type inference that drops
  unlisted JSON string fields in the first place.
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

**Status: done.** A narrow slice of Milestone 6 (AI Assistant) was pulled
forward alongside this milestone: `POST /api/ai/sql`, backed by a local
Ollama model, is implemented now so the Panel builder can offer an AI-only
natural-language query builder — by design, no manual/visual query builder
was built at all; SQL is only ever produced by hand-editing the generated
statement or asking the AI again. SQL explanation and the other AI
endpoints remain deferred to the real Milestone 6.

All three initial follow-ups are now closed, sharing one Grafana-style
textual-macro substitution mechanism (`app/shared/sql_macros.py` +
`app/shared/time_range.py`, applied in `DashboardService`):

- **Dashboard time range picker** now filters every panel query: SQL can
  reference `$__timeFrom`/`$__timeTo`, resolved server-side per request via
  `POST /api/dashboard/{id}/panel/{panel_id}/query` (saved panels) and
  `POST /api/dashboard/{id}/preview-query` (ad hoc SQL in the Panel Builder).
- **Variable Builder** (`frontend/src/pages/VariableBuilder.tsx`) replaces
  the old placeholder — a dedicated page mirroring the Panel Builder's
  layout (form + `SchemaBrowser`). Fully schema-driven, no free-typed
  text/number/options and no hand-written or AI-written SQL: a variable is
  created by clicking a value column in the schema browser, and optionally a
  second, same-table predicate column filtered by an explicitly-picked
  earlier variable. The backend derives
  `SELECT DISTINCT value_column FROM table [WHERE predicate_column =
  $predicate_variable]` (`build_variable_source_sql`, `dashboard/models.py`)
  and resolves it via `POST /api/dashboard/{id}/variables/options` — this
  gives Grafana-style chained/cascading variables (e.g. Project → Device)
  without a dependency graph, since a variable's `predicate_variable` may
  only reference a variable defined earlier in the list (enforced by
  `validate_variables`). Panel Builder's SQL preview and the AI SQL builder
  (`build_sql_prompt`) both now resolve/reference live dashboard variables
  correctly — previously the preview silently dropped `$variable` values and
  the AI prompt had no awareness variables existed.
- **Dual-axis / multi-series panels**: `LineChart`/`BarChart`/`ScatterChart`
  keep `y_axis` as the first series and add `series: list[SeriesConfig]`
  for additional series, each with its own `field`, `axis` (`left`/`right`),
  and optional `type` override (inherits the parent chart's type when
  omitted) — additive, no data migration needed. `PanelEditor.tsx` has an
  add/remove series-row UI; `charts/options.ts` emits a second `yAxis` when
  any series uses the right axis.

A fourth follow-up, long-format ("melted"/tidy) chart data, is also now
closed — found while testing the AI query builder against a real
device-metrics/device-status join: a request like "humidity and
uptime_seconds per device" naturally produces long-format rows (`time,
variable, value`) rather than one column per series, which the wide-format-only
`Chart` model (`y_axis` + `series: list[SeriesConfig]`) had no way to
render. Unlike the three follow-ups above, this one is purely a client-side
rendering/config change, not part of the SQL-macro mechanism:

- **Long-format charts**: `LineChart`/`BarChart`/`ScatterChart` gained an
  optional `series_by: str | None` field (mutually exclusive with `series`,
  enforced by a validator — reusing `y_axis` as "the value column" rather
  than adding a redundant field). When set, `buildXyOption`
  (`frontend/src/charts/options.ts`) groups rows by each distinct
  `series_by` value into its own independent `[x, value]` point list,
  plotted on a real `xAxis: {type: "time"}` rather than a shared category
  axis. That distinction mattered in practice: a first version aligned all
  series to one shared, deduped x-value list and padded gaps with `null`,
  which only works when series share exact timestamps (e.g. two metrics
  unioned from the same underlying rows) — it silently broke for the actual
  motivating case, splitting by `device_id`, where each device reports at
  its own independent timestamp, leaving every series as isolated dots with
  nothing to connect. `PanelEditor.tsx` adds a "Split Series By" column
  picker that hides the (mutually exclusive) dual-axis series UI when
  active. v1 renders all long-format series on a single left axis only,
  since distinct series names are discovered at query time rather than
  known statically the way dual-axis's per-field axis assignment requires.

The fifth and final follow-up, dashboard auto-refresh interval, is now
closed, and with it Milestone 3 has no more open follow-ups.

- **Dashboard auto-refresh**: a "Refresh" dropdown (`constants/refreshIntervals.ts`
  — Off/10s/30s/1m/5m, default 10s) sits next to the time range picker in
  `DashboardEditor.tsx`'s toolbar. A `setInterval`/`useEffect` re-runs the
  same `refreshPanelData` already used for load/variable/time-range changes,
  cleared on interval change or unmount. Dashboard-level only, matching the
  existing time-range picker's precedent: `DashboardEditor` already applies
  one dashboard-wide time range to every panel unconditionally, ignoring
  each panel's own persisted `time_range` default, so treating refresh the
  same way is consistent rather than introducing a second, differently-scoped
  override concept. `Panel.refresh_interval: int = 0`
  (`backend/app/dashboard/models.py`) remains dormant/unused, same as
  before — wiring it up would need new per-panel override plumbing with no
  existing precedent, whereas the dashboard-level toggle needed zero backend
  changes.

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

**Status: done.** `examples/beekeeping-simulator/` (sibling to
`examples/mqtt-publisher/`) simulates 2 apiaries × 3 hives (6 hives total)
publishing temperature/humidity/weight to `beekeeping/hive` over MQTT, using
a small bounded random walk per hive (reverting toward a healthy-brood-nest
midpoint for temperature/humidity, slow net-upward drift for weight) so
charts read as plausible sensor data rather than pure noise.

Unlike `mqtt-publisher`, this showcase also provisions its own Collector and
Dashboard on startup — a new pattern for this repo (`seed.py`, using
`requests` against the backend's own REST API, looked up by name and reused
rather than duplicated on every restart, since nothing in this compose setup
gates container start on the backend/Mongo/Timescale actually being ready to
serve — the seed step retries with backoff itself). One container
(`main.py`) runs the idempotent seed step once, then hands off to the
long-running hive-telemetry publish loop.

The Dashboard doubles as a live demonstration of two Milestone 3 features
built the same week: chained/predicate variables (`apiary` → `hive`, mirroring
the Project → Device example already documented for the Variable Builder)
and long-format charts (`series_by`), used in two different scopes to make
the distinction concrete rather than accidentally conflating them — "Apiary
Hives Temperature" filters by the selected `$apiary` only and splits that
apiary's 3 hives into one line each, while "All Hives Weight" carries no
variable filter at all and always splits all 6 hives, across both apiaries,
into one line each. Both read from one query each — never one line per
hardcoded column.

`docker-compose.yml` gates the whole thing behind its own `beekeeping`
profile (not `tools`, since this is the flagship v1 demo, not a manual
verification tool) with `restart: unless-stopped` — the one deliberate
deviation from `mqtt-publisher`'s pattern, since a transient MQTT/DB blip
silently killing the flagship demo's data flow is a worse failure mode here
than for a dev-only tool. Confirmed via `docker compose --profile beekeeping
config --services` that Compose always includes every service with no
`profiles:` key regardless of which profile is requested — so `docker
compose --profile beekeeping up -d` alone is the literal one command that
takes a fully cold stop to a live, populated dashboard, satisfying both this
milestone's acceptance criteria and the [v1 Definition of
Done](#v1-definition-of-done) bullet below verbatim.

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

**Status: core engine done (2026-07-10); beekeeping swarm-alert wiring not
started.** First two acceptance criteria are met and verified live against
the real stack (not just unit-level): a real MQTT message crossing a rule's
threshold gets tagged/deduped by `custom-telegraf`'s `processors.rule` and
enqueued by its `outputs.celery`, consumed by a real Python `celery` worker
(`app/automater/tasks.py`, new `celery-worker` compose service) within
milliseconds. The third — wiring an actual swarm-alert rule into the
beekeeping showcase itself — is **not** done; verification instead used a
dedicated `examples/rule-testing-publisher` fixture (a "Rule Testing
Sandbox" project with its own Collector, deliberately covering tags,
numeric fields, and string fields across two tables) built specifically so
rule-condition scenarios could be exercised without touching the showcase.
Full detail — day-by-day, including several bugs found and fixed along the
way — lives in `iotops-workspace/ROADMAP.md`, not duplicated here; short
version:

- Real Rule/Condition models, `RuleProcessorConfig`/`CeleryOutputConfig`
  registered like any other plugin, `generate_toml` generalized to a shared
  `Pipeline` base Collector and Automater both extend.
- `processors.rule` (Go): real match/clear firing-state semantics via
  Redis (`SETNX`-with-TTL / `DEL`, not just one-shot dedup), every enabled
  rule on a matching table evaluated independently (not first-match-wins),
  firing keys scoped by Rule `id` (not `name` — names are deliberately not
  required unique), per-condition `AND`/`OR` chains folded strictly
  left-to-right (`Rule.operator` removed in favor of `Condition.join`, so
  `a==1 AND b>3 OR c<5` is expressible), condition lookups check both tags
  and fields.
- `outputs.celery` (Go): real Celery protocol v2 envelope, `LPUSH`ed onto
  Redis, consumed by an unmodified Python `celery` worker with no
  compatibility shim.
- Automater and Rule are independently addressable: a project can have any
  number of Automaters (never restricted to one, mirrors Collector); Rule
  has its own lifecycle (activate/deactivate/delete) distinct from its
  Automater's (deploy/stop/delete); an Automater can watch more than one
  table (gains a new mqtt input, derived from a chosen Collector, the first
  time a rule needs a table it doesn't already cover).
- Frontend: rule-creation flow (Project → Automater picker, existing or
  new → Collector picker when one's needed → rule metadata + DB-schema-
  driven condition builder, filtered to the selected project/Collector's
  own tables), automater-cards-with-nested-rule-tables list view with
  confirm-gated Stop/Deactivate/Delete actions.
- Zero automated tests either repo — explicitly deferred, next up now that
  the engine itself has substantially settled.

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
