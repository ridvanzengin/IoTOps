# Development Plan

Version: 0.3.0 (Phased Roadmap)

For dated, compressed history of what's already shipped, see
[CHANGELOG.md](../CHANGELOG.md).

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

**Status: core engine done and substantially extended beyond the original
scope (through 2026-07-14).** First two acceptance criteria are met and
verified live against the real stack (not just unit-level): a real MQTT
message crossing a rule's threshold gets tagged/deduped by
`custom-telegraf`'s `processors.rule` and enqueued by its `outputs.celery`,
consumed by a real Python `celery` worker (`app/automater/tasks.py`, new
`celery-worker` compose service) within milliseconds. The third — wiring an
actual swarm-alert rule into the beekeeping showcase itself — was
deliberately descoped, not just deferred: verification instead used a
dedicated `examples/rule-testing-publisher` fixture (a "Rule Testing
Sandbox" project with its own Collector, deliberately covering tags,
numeric fields, and string fields across two tables) built specifically so
rule-condition scenarios could be exercised without touching the showcase.
Full dated history lives in [CHANGELOG.md](../CHANGELOG.md); short version:

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
- ~~Zero automated tests either repo~~ Addressed 2026-07-10 (32 new tests
  across both repos, plus fixed 7 pre-existing `collector`/`plugin` tests
  that had silently broken during the `Pipeline` extraction).
- New, beyond the original milestone scope: a persisted `Event` model
  (Mongo) and a project-scoped, live-updating (Server-Sent Events) Events
  sidebar, redesigned 2026-07-11 through 2026-07-13 around a VSCode-style
  activity bar (one icon per project, unresolved-match badge counts,
  occurrence card redesign), events overlaying directly on Panel charts,
  and clicking an occurrence card's identifier setting a matching
  dashboard variable. Rules also gained a `resolve_mode`
  (auto-clear/manual-resolve). See CHANGELOG.md's 2026-07-10 through
  2026-07-13 entries.
- **Query Rules (2026-07-14), a second major extension beyond the
  original milestone scope**: scheduled, SQL-based rules for
  cross-table/cross-metric correlation the real-time per-metric Go
  pipeline can't express (time-windowed aggregates, arbitrary AND/OR
  nesting across tables), evaluated via Celery Beat rather than Telegraf.
  Reuses the entire Events pipeline (pairing, SSE, overlays,
  manual-resolve) unmodified. See CHANGELOG.md's 2026-07-14 entry.

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

**Status: SQL generation shipped early (Milestone 3, `POST /api/ai/sql`,
originally Ollama-backed, later migrated onto Anthropic — see below).
Slice 1 of the Co-pilot (Q&A over stored data) shipped 2026-07-16.** The
activity bar's reserved Co-pilot panel slot (`EventsContext.tsx`'s
`ActivePanel`'s `{ kind: "copilot" }` case) now renders a real
`CopilotChat.tsx` component instead of a placeholder.

The Co-pilot chat uses the user's own Anthropic API key, model
`claude-haiku-4-5` — a deliberate choice for this portfolio project, to
demonstrate real Claude API usage (including tool calling) on a small
budget. SQL generation originally stayed on a separate local Ollama model
backend; it was later switched onto the same Anthropic client as the
Co-pilot (see CHANGELOG.md), so there's now a single AI backend for the
whole app.

Architecture: real tool-calling (a manual iteration loop —
`MAX_COPILOT_ITERATIONS = 10`, bumped from an original 4 once a real
cross-table suggestion request needed more round-trips than that — in
`AiService.answer_copilot_question`, `backend/app/ai/service.py`), not
context-stuffing — the model calls tools on demand rather than having
occurrences pre-fetched into every prompt:
- `query_occurrences` (`backend/app/ai/tools.py`) — structured Event/
  Occurrence lookup, `project_id` bound server-side (never model-facing).
- `query_telemetry` — model-written read-only SQL, reusing the existing
  `validate_select_only_sql` guardrail plus a new row cap and 10s timeout
  (`TelemetryService.run_bounded_query`, addressing the "no runaway-query
  timeout" gap in Known Issues below, at least for this call site).
- `flag_missing_context`, `list_existing_rules`, `suggest_automation` —
  added for later slices, see below. All five tools are always in the
  model's tool list now, in every conversation — see "Lesson learned"
  under Slice 2 below for why that wasn't the original design.

This unlocks real telemetry-*value* Q&A ("what was the temperature at
3pm") that a context-stuffing design couldn't answer. Verified end-to-end
against live demo data (real occurrence counts/timestamps, real telemetry
averages cross-checked against TimescaleDB directly) — see CHANGELOG.md's
2026-07-16 entry. Measured cost: ~$0.008/question, comfortably within the
project's $5 budget.

**Scope for the remaining two slices**:

1. ~~Q&A over what's already stored~~ **Done** — see above.
2. ~~**Rule suggestions**~~ **Done (2026-07-17, PR #22).** Proposes a new
   real-time Automater Rule or scheduled Query Rule from real telemetry
   stats + existing-rule awareness, pre-filled into the existing
   rule-creation form rather than silently auto-created. See
   CHANGELOG.md's 2026-07-17/2026-07-18 entries and "Future — Suggested
   Dashboards & Automations" below for the shipped design (the
   entry-point/refinement/interoperability decisions there are still
   accurate; the *tool-availability-gated-by-intent* part is superseded,
   see the lesson-learned callout right below it).
3. **Dashboard/panel suggestions** — same idea, proposing a chart from a
   schema + usage pattern, landing in the Panel Builder. Not yet built.

**Lesson learned building Slice 2, apply to Slice 3 from the start:**
`suggest_automation`/`list_existing_rules` were originally gated behind
an `intent="suggest-automation"` flag, only set when the panel was opened
via the dedicated button — the plan below still describes that design. A
real user session showed a plain "I want to create a rule" typed into
the ordinary Co-pilot hitting a dead end ("I don't have the ability to
create rules") because the tool genuinely wasn't attached to that
conversation. Fixed by making all five tools always available in every
conversation, gated only by the model's own judgment (the same way it
already avoids misusing `query_occurrences` on an unrelated question) —
not by an externally-set flag. **`suggest_panel`/`suggest_dashboard`
should be always-on tools from the start, not intent-gated**; keep
`intent` only for what it's still legitimately useful for — UI framing
(an intent-aware greeting) and, for panel-suggestion specifically,
skipping the project-picker step when `dashboardId`/`projectId` are
already known from context.

All three "Suggest..." entry points route through the Co-pilot chat (not
separate prefilled-form buttons), reusing the tool-calling loop and
structured-output pattern already built for slice 1 — Slice 2 proved this
pattern end to end (including a live-tested quick-replies mechanism for
multi-choice/confirmation questions, and prompt tuning for brevity and
proposing a fast draft over interrogating for every parameter); Slice 3
reuses it as designed.

---

# Portfolio Demo Deployment

**Requirement**: deploy a public demo without waiting for the rest of the
roadmap (additional data sources, AI Co-pilot) to land — current state (v1
+ most of Milestone 5) is already demo-worthy. Two decisions already
confirmed:

- **Hosting: a single small VM running the existing `docker-compose.yml`
  as-is** (not a managed container platform) — closest to zero
  re-architecting, matches local dev almost exactly.
- **Interactivity: read-only showcase, not fully interactive.** The
  backend spawns real Docker containers per Collector/Automater via the
  host Docker socket — letting the public internet trigger that with no
  auth/quotas/cleanup is a real attack surface, so the public demo runs
  the Beekeeping Showcase (and/or Rule Testing Sandbox) continuously
  server-side, but doesn't let anonymous visitors create their own
  Collectors/Automaters.

**Status: DONE. Live at https://iotops.online as of 2026-07-16.** All 3
demo scenarios (Apiary/MQTT, Solar/HTTP, Manufacturing/Kafka) work end to
end. See CHANGELOG.md's 2026-07-16 entry for the full list of real bugs
this surfaced, `deploy/SERVER_SETUP.md` for the numbered setup playbook,
and the `/deploy` skill (`.claude/skills/deploy/SKILL.md`) for the
routine-update flow and troubleshooting.

1. ~~Server-side read-only enforcement~~ **Done.** `Settings.demo: bool`
   (`backend/app/config.py`) + `block_in_demo_mode()`
   (`backend/app/dependencies.py`) — a dependency factory raising
   `DemoModeError`, wired per-route via
   `dependencies=[Depends(block_in_demo_mode())]` on every mutating
   Collector/Automater/AI route, not just hidden client-side. A scoped
   `X-Demo-Seed-Token` bypass lets `examples/demo/seed.py`'s own
   provisioning through on just the specific create/update routes it
   calls — every delete/stop route and everything outside
   Project/Collector/Automater/QueryRule/Dashboard stays hard-blocked
   regardless of the token.
2. ~~Showcase data needs to look alive, not static~~ **Done.** A
   dedicated `demo-showcase` compose service (`examples/demo/`) seeds its
   own Apiary/Solar/Manufacturing showcase content and publishes
   continuously.
3. ~~Reverse proxy + TLS~~ **Done.** Reused the shared VM's existing
   `infra` Compose project exactly as planned below — `infra-nginx-1`
   (nginx vhost at `deploy/nginx/iotops.conf`), `infra-db-1` (a real
   `iotops` database/user on the shared TimescaleDB instance),
   `infra-redis-1` (own logical DB indices). A valid Let's Encrypt cert
   auto-renews via the VM's existing cron (one `certbot renew` line
   already covers every cert on the box, not just AgriTwin's). Mongo/
   Mosquitto/Kafka run in IoTOps's own Compose project on the shared
   `infra_proxy` network, no host ports published. The frontend runs a
   real production build (`docker/frontend/Dockerfile.prod`, multi-stage
   with nginx serving static output) rather than Vite's dev server.
4. ~~Needs the user's hands-on involvement~~ **Done.** Domain purchased
   and pointed at the VM, VM access confirmed, systemd
   (`iotops-app.service`) auto-starts the stack on reboot.

Merged into `main` via PR #18 as of 2026-07-16 — 15 commits: the infra
scaffolding, several real bugs found only by actually running the
deployment (not just planning it), Kafka enablement, and a `/deploy`
skill capturing the whole playbook for next time.

---

# Known Issues

Real, non-blocking gaps — not prioritized/sequenced beyond what's noted.
Fix opportunistically, not preemptively.

- **Asymmetric Redis-error handling in `rule.go`.** `trySetFiring` fails
  *open* on a Redis error (risk: duplicate match). `clearFiring` fails
  *closed* (risk: a clear silently drops, occurrence looks permanently
  unresolved until the firing key expires on its own TTL with no
  explicit clear ever logged). Worth a bounded retry on `clearFiring`, or
  at minimum loud logging when it happens.
- **Unexplained ~90-minute MQTT reconnect gap**, recurred more than once.
  Stock Telegraf `inputs.mqtt_consumer`, not custom code; resolved by a
  container restart each time, never root-caused. No healthcheck or
  alerting on "container up but not receiving."
- **No flapping/hysteresis protection.** A value oscillating right at a
  threshold fires a match/clear pair on every single crossing.
- **No server-side validation that Rule `identifiers`/`message`
  placeholders are actually in the input's `tag_keys`.** Today it's a
  frontend-only warning (`AutomaterEditor.tsx`) — a column missing from
  `tag_keys` silently renders empty in the interpolated message
  (`"Hive  swarm risk"` instead of `"Hive hive1 swarm risk"`), and
  anyone hitting the API directly gets no protection at all.
- **No image build/publish pipeline for `custom-telegraf`** —
  `custom-telegraf:latest` is built by hand, now on the production VM too
  (documented as its own step in `deploy/SERVER_SETUP.md`, after the very
  first deployment ran without it and every Automater deploy 404'd). A
  real CI/CD pipeline (build + push to a registry, pull by tag) is still
  the actual gap; hand-building on each host it needs to run on on is a
  workaround, not a fix.
- **Stale mqtt inputs on multi-table Automaters aren't garbage
  collected** (deliberate). An Automater that loses its last rule for one
  of its tables keeps the now-unused mqtt input in its deployed config
  indefinitely — harmless (wasted subscription, no incorrect behavior),
  not worth the GC logic unless it becomes an actual operational
  nuisance.
- **No runaway-query timeout on interactive Panel queries.** Query Rules'
  scheduled evaluation has a hard 10s `asyncpg` timeout
  (`TelemetryRepository.execute_match_query`); the equivalent
  interactive path (Panel Builder's ad hoc SQL) has none at all. One
  concrete vector through this gap is closed (2026-07-18): allowing `WITH`
  in `validate_select_only_sql` (for AI-suggested CTEs) briefly reopened
  it to `WITH RECURSIVE` specifically, since Postgres can spin forever on
  an unbounded recursive CTE with no query-level timeout to stop it —
  `RECURSIVE` is now in the forbidden-keyword blocklist. The general gap
  (any ordinary long-running query, recursive or not, still has no
  timeout on this path) remains open.

---

# Future — Suggested Dashboards & Automations

Milestone 6's remaining two slices (rule suggestions, panel/dashboard
suggestions). **Design decided 2026-07-17; rule suggestions shipped the
same day** (see CHANGELOG.md's 2026-07-17 entry) — this supersedes the
standalone-single-shot-endpoint sketch this section previously had
(`POST /api/ai/dashboard` / `POST /api/ai/automation` as plain generation
endpoints, a model-selection dropdown). Both ideas are superseded by
routing everything through the Co-pilot chat instead — see below for why.
Panel/dashboard suggestions are still unbuilt; the design below is the
plan for those, and doubles as a record of what rule suggestions already
implemented.

## Decided: all three "Suggest..." entry points open the Co-pilot, not a separate prefilled-form flow

> **Superseded in one specific way (2026-07-18):** the "per-intent system
> prompt switches in the tool" and "branching logic lives in the prompt"
> language below described gating *tool availability* on `intent`. That
> part didn't survive contact with a real user — see the "Lesson learned"
> callout earlier in this doc (under Milestone 6). `suggest_automation`/
> `list_existing_rules` are unconditionally in the tool list now; the
> model decides when to use them from the conversation itself. Everything
> else below (opening the Co-pilot with an intent rather than a separate
> form, the `dashboardId`/`projectId` shortcut for panel-suggestion, the
> three suggestion tools' own read-only introspection) is still the plan.

"Suggest an automation" (on the Automaters/Query Rules list pages),
"Suggest a dashboard" (on the Dashboards page), and "Suggest a panel" (a
new option in an existing dashboard's `+` dropdown) all call
`openCopilotPanel()` with an **intent** (`suggest-automation` /
`suggest-dashboard` / `suggest-panel`), rather than navigating straight to
a prefilled form. Reasoning: the interesting part of "suggest an
automation" isn't generation, it's the back-and-forth ("do you have
something in mind, or should I suggest one?", "should this be an overview
dashboard or should I create variables?") — a real conversation handles
arbitrary answers (including a fully-specified request arriving in one
message) far better than a hardcoded decision tree of scripted UI prompts.

- `ActivePanel`'s `{ kind: "copilot" }` case gains an optional intent field
  (and, for the panel-suggestion entry point specifically, the
  already-known `dashboardId`/`projectId` — no "which project?" step needed
  there, since it's opened from inside an already-open dashboard). This
  part shipped for `suggest-automation` as planned — `intent` is a real,
  still-used `CopilotChat.tsx` prop, just UI framing only now (greeting
  text, seed chip), never sent to the backend.
- ~~The existing scripted greeting/project-picker (`CopilotChat.tsx`) stays
  exactly as shipped for the other two intents — free, deterministic, no
  model call. Once a project is picked, `CopilotChat` switches to a
  per-intent system prompt that instructs the model what to ask and when
  to stop asking and call the suggestion tool. The branching logic lives in
  the prompt, not in frontend code.~~ The greeting/project-picker part
  still holds; the tool-switching part doesn't — see the superseded note
  above.
- Three new tools alongside `query_occurrences`/`query_telemetry`:
  `suggest_automation` (shipped, always available), `suggest_panel`,
  `suggest_dashboard` (not yet built — build these always-available too).
  Each does its own read-only introspection before proposing anything:
  - **What already exists** — a new read tool over current Rules/
    Automaters (for `suggest_automation`) or Panels/Variables (for
    `suggest_panel`/`suggest_dashboard`), so the model doesn't propose a
    duplicate and can spot actual coverage gaps.
  - **Real telemetry statistics, not just column names** — reuses the
    `query_telemetry`-style bounded read-only SQL tool to run its own
    `min`/`max`/`avg`/`percentile_cont` queries before proposing a
    threshold or chart. This is what turns "temperature > 30" (useless —
    always true against real hive data, which runs 33-40°C) into "> 38"
    (the actual inflection point, matching what the live demo's real rules
    already use) — without this, a threshold suggestion is just a guess.
  - **Domain knowledge** — Claude's own general knowledge (e.g. "elevated
    hive temperature indicates colony stress"), calibrated against the two
    ingredients above rather than fed in separately.
- Response shape changes: `CopilotAnswerResponse` gains an optional
  `suggestion` field (a discriminated union on `kind`) alongside `answer`,
  populated whenever the tool-calling loop's last executed tool was a
  `suggest_*` tool — e.g. `{kind: "panel", label: "...", navigateTo:
  "/dashboards/{id}", state: {...}}`. The frontend renders this as a link
  card in the chat transcript (not just prose), navigating via React
  Router `state` (same mechanism a plain "Suggest an automation" button
  would have used) into the relevant builder, pre-filled — never
  auto-created, same reviewable-draft principle as before.

## Decided: refinement is continued conversation, not a new mechanism

After a `suggestion` card is presented, the conversation doesn't end —
a follow-up like "use max instead of average" or "split by apiary instead
of hive" is a refinement request, not a new question, and the per-intent
system prompt should tell the model to treat it that way: call the same
`suggest_*` tool again with the adjustment and present an updated card.
No new backend mechanism needed — this falls out of the tool-calling loop
already built, just prompted to expect iteration.

**Where the line sits**: chat refinement is for adjusting the *shape* of a
proposal before committing to it (chart type, aggregation, grouping,
threshold) — not a replacement for editing in the builder. Once the user
clicks through, the Panel Builder / Rule form is already a fully editable
surface; there's no reason to duplicate that inside the chat.

**One real technical gotcha to design in from the start**: the Q&A
slice's stateless-history design means only the *prose* of a past turn
round-trips back to the model on the next request — never the literal
structured `suggestion` payload (the actual SQL/conditions/chart config),
since tool-use messages are internal to one request (see slice 1's
"Multi-turn history" decision above). If a refinement turn only has the
model's own vague recollection of what it suggested, "use max instead"
risks silently regenerating the whole proposal instead of changing one
field. Fix: whenever a `suggestion` is present, append a compact
machine-readable recap to the assistant message's stored `content` (the
text that actually round-trips as history) — not just the friendly prose
shown in the bubble — so a refinement request is grounded on the exact
prior SQL/conditions, not a paraphrase.

## The one part that's a bigger lift: "Suggest a dashboard"

"Suggest a panel" and "Suggest an automation" both land in an *existing*
form (Panel Builder / Rule creation form) via the same prefill mechanism.
"Suggest a dashboard" doesn't have an existing form to prefill — it needs
a new **in-memory draft dashboard** state in the Dashboard Editor (name +
variables + panels, nothing persisted until an explicit Save), since
today's editor always operates on an already-persisted dashboard. Also
worth deciding as part of that flow: whether the dashboard should be a
flat "overview" (no variables) or use chained variables (e.g. Apiary →
Hive, mirroring the existing Beekeeping showcase pattern) — per the
"decided" section above, this should be asked conversationally, not
hardcoded as a toggle.

## Recommended build order

1. ~~**Rule suggestions**~~ **Done (2026-07-17, PR #22)** — smallest
   complete vertical slice (panel open → conversational clarification →
   `suggest_automation` tool → suggestion card → prefilled
   `/automaters/new` or `/query-rules/new`). Proved the whole pattern end
   to end, including several rounds of live verification against the real
   Anthropic API (not just mocks) that each surfaced a real bug mocks
   alone didn't catch — see CHANGELOG.md's 2026-07-17/2026-07-18 entries.
   Biggest one: tool availability gated by entry-point `intent` broke a
   plain "I want to create a rule" typed into the ordinary Co-pilot; fixed
   by making the tools always-available (see the "Lesson learned" callout
   above) — build Slices 2/3 that way from the start next time, skip
   re-discovering this the hard way.
2. **Panel suggestions** — not yet started. Reuses the same pattern;
   smaller lift since it plugs into the existing Panel Builder prefill
   flow (already used by the NL-to-SQL button), just model-initiated
   instead of user-typed.
3. **Dashboard suggestions** — last, since it needs the new draft-editor
   capability above.

## One concrete constraint to keep in mind once suggestion logic gets built

Rule `identifiers` and Dashboard `Variable.value_column`s have no enforced
relationship, but two shipped features already depend on them matching by
name (overlay-events time-window filtering, and clicking an occurrence
card identifier to set a dashboard variable). When a suggestion proposes a
new Rule or Dashboard Variable referencing the same underlying column, it
should keep the identifier key and the `value_column` spelled identically
— not a schema change, just a suggestion-quality constraint to design in
from the start rather than have suggested rules and dashboards silently
fail to interoperate.

---

# Project-Level AI Context Helper

**Status: shipped 2026-07-17.** Every AI feature before this grounded
itself in the telemetry schema alone (table/column names + types) — this
works well for the demo showcases (`temperature`, `hive_id`, `weight` are
self-explanatory) but doesn't generalize to real-world telemetry, where
column names are often opaque (`val1`, `sensor_a`, coded status enums) and
no amount of statistics-querying (see the suggestion tools above) fixes a
name the model can't interpret in the first place. IoTOps is meant to be
domain-agnostic, so this gap matters beyond the showcases.

Built and shipped together: the `Project.ai_context` field itself, its
`ProjectForm.tsx` textarea (with character counter and `focusField`
support), injection into `build_copilot_system_prompt`, and the **smart
nudge** — a new `flag_missing_context` tool the model calls (instead of
guessing) when a column's meaning is genuinely unclear, surfaced as
`CopilotAnswerResponse.needs_context` and rendered as an inline "add
context" link in `CopilotChat.tsx`. The static-icon discoverability idea
described below was **not** built — the smart nudge alone was judged
sufficient for a first version, since it only appears when actually
relevant rather than nagging on every project regardless of whether its
schema is already clear. Still not built: extending `ai_context` to the
`build_sql_prompt`/`build_query_rule_sql_prompt` SQL-generation prompts, and the
related pre-existing schema-scoping gap noted below.

**Design**: a new `Project.ai_context: str = ""` field, capped at
**1000 characters** (`Field(max_length=1000)` server-side, `maxLength` +
a running character counter client-side) — it's injected into every AI
prompt for that project, so it needs a hard cost/context-bloat cap, not
just a soft suggestion; 1000 chars is plenty for several column-meaning
notes without becoming a pasted-in runbook. Deliberately **not** reusing
the existing `Project.description` — that's a short human-facing blurb
shown in project lists/cards; this is a longer, AI-only domain glossary,
and conflating the two would mean editing one silently changes the
other's behavior.

**Lives on the Project, not the Collector.** A Collector is an
infrastructure object (topic/table/field-mapping wiring); putting a
domain-knowledge field there would leak an AI concern into a form whose
job is Telegraf pipeline config. A Project is already the "what this
deployment is about" object, and in practice one project maps to one
coherent domain (per the existing showcases) — even where a project's
several Collectors write to genuinely different tables, the free-text
field can just say so inline ("`machine_telemetry.val1` = vibration;
`env_readings.val1` = humidity") rather than needing a field per
Collector. One place to look, one place to edit.

Edited via a new textarea in `ProjectForm.tsx`, framed as e.g. "Optional —
help the AI understand your data" with placeholder text like "e.g. `val1`
is coolant temperature in °C, `sensor_a` tracks primary shaft vibration."
Optional and empty by default; an escape hatch for unclear schemas, not a
required step.

**Discoverability — shipped: the smarter, model-driven nudge. Not built: the static icon.**
- **Shipped**: `flag_missing_context(column, reason)` — a lightweight tool
  the model calls when it judges a column's meaning is genuinely unclear
  and no `ai_context` covers it, rather than guessing or trying to detect
  this by string-matching its prose answer (fragile). `CopilotAnswerResponse`
  gains `needs_context: {column, reason} | null` alongside `answer` (the
  same "structured field next to the prose answer" pattern used for the
  future `suggestion` field), and `CopilotChat.tsx` renders an inline nudge
  under that specific answer ("I wasn't sure what `val1` means — add
  context →") linking to
  `navigate("/projects/{id}/edit", { state: { focusField: "ai_context" } })`
  — `ProjectForm.tsx` reads `location.state.focusField` and focuses/scrolls
  to the textarea. This alone was judged sufficient for a first version:
  it only appears when actually relevant, unlike a generic icon that would
  nag on every project regardless of whether its schema is already clear
  (like the demo showcases, where this should basically never fire).
- **Not built**: the static (i) icon near the project picker, always
  visible once a project is chosen regardless of whether the model has
  ever struggled. Would reuse the same `state`-carrying navigation as
  above — cheap to add later if the model-driven nudge alone proves too
  rare/easy to miss in practice.

**Where it's used**: appended to the schema block in `build_copilot_system_prompt`
(Q&A slice) and, once built, the future `suggest_*` tools — framed
explicitly as user-provided domain context to trust over guessing from
column names alone. Still not extended to the existing
`build_sql_prompt`/`build_query_rule_sql_prompt` — the same
ambiguous-column-name problem applies there, but that's a separate,
smaller addition not yet done.

**Trust model**: no new security concern — this is free text supplied by
the project's own owner (same trust level as a Rule's message template or
a Dashboard's name, both already user-authored and already fed into
prompts/UI), not untrusted input from an anonymous/public-demo user. The
existing demo-mode gate already blocks every mutating/AI route for
anonymous visitors regardless.

**Related, pre-existing gap worth noting** (not required to build this,
but relevant context): `TelemetryService.get_schema()` returns *every*
hypertable across *all* projects, not scoped to the querying project's own
Collectors — so today's schema block in every AI prompt already includes
tables that have nothing to do with the project being asked about. Adding
per-project context text doesn't fix this by itself; scoping the schema
block to only the tables a project's own Collectors actually write to
(derivable from each Collector's TimescaleDB output config) would be a
natural companion improvement, but is a separate, un-scoped decision — not
bundled into this one.

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

Although the UI exposes **Collector** and **Automater**, the backend internally uses a shared **Pipeline** model.

**Status: done (2026-07-08, as part of Milestone 5 Phase B).**
`app/shared/models.py` now has `Pipeline`/`InputPlugin`/`ProcessorPlugin`/
`OutputPlugin`/`DockerConfig`; `CollectorPluginsBase(Pipeline)` adds
`processors`, `AutomaterPluginsBase(Pipeline)` adds `rules: list[Rule]`.
`generate_toml(inputs, processors, outputs, registry)` is shared by both
`CollectorService.deploy()` and `AutomaterService.deploy()`. Collector's
existing behavior was regression-checked against the extraction and is
unaffected.

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

v1 (Milestones 0–4) and v1.1's core engine (Milestone 5, including the
Query Rules and Events sidebar extensions beyond its original scope) are
both done and demo-worthy. Recommended next step: **Portfolio Demo
Deployment** (above) — server-side read-only enforcement is the one
genuinely blocking piece (there is no auth of any kind today), everything
else there is infra work. AI Co-pilot (Milestone 6) and additional domain
showcases (below) remain fast-follows after the demo ships, not
blockers — same reasoning that kept Automation/AI off v1's own critical
path.
