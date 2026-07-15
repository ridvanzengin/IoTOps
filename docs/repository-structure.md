# Repository Structure

Version: 0.1.0

---

# Philosophy

The repository is organized around business domains rather than technologies.

Avoid structures like

backend/
    routes/
    models/
    services/

Instead prefer

backend/
    collector/
    automater/
    dashboard/
    plugins/

Each module owns its API, models, services and business logic.

---

# Repository Layout

iotops/

│

├── backend/

├── frontend/

├── plugins/

├── runtime/

├── docs/

├── scripts/

├── docker/

├── examples/

├── tests/

├── docker-compose.yml

├── README.md

└── .env.example

---

# Backend Layout

backend/

    app/

        main.py

        config.py

        dependencies.py

        database.py

        ai/

        collector/

        automater/

        dashboard/

        plugin/

        project/

        telemetry/

        shared/

Each directory represents a domain. `docker.py` lives inside `collector/`
(Docker lifecycle is a Collector concern), not at the app root.

`automater/` is not implemented yet (Milestone 5). `dashboard/`, `ai/`, and
`project/` are implemented as of Milestone 3. `telemetry/` was added ahead
of a dedicated domain-model doc entry — see its own section below.

---

# Project Module

project/

    api.py

    models.py

    service.py

    repository.py

Responsibilities

- project CRUD

Intentionally the simplest module in the backend — no runtime lifecycle,
no plugins, no validation beyond required fields. Follows the same
`api.py -> service.py -> repository.py` layering and Mongo `_id`-keyed
document convention as every other domain module (see
[domain-models.md](domain-models.md#project)).

---

# Collector Module

collector/

    api.py

    models.py

    service.py

    repository.py

    generator.py

    docker.py

Responsibilities

- collector CRUD

- generate telegraf.conf

- docker lifecycle

- validation

---

# Automater Module

automater/

    api.py

    models.py

    service.py

    repository.py

Responsibilities

- rule management

- automater CRUD

- deployment

---

# Dashboard Module

dashboard/

    api.py

    models.py

    service.py

    repository.py

Responsibilities

- dashboards

- panels

- variables

- layouts

---

# Plugin Module

plugin/

    api.py

    models.py

    registry.py

    common.py

    inputs/

    outputs/

Responsibilities

- plugin registry

- plugin metadata

- schema lookup

TOML generation itself lives in `collector/generator.py` (it turns a
Collector's resolved plugin configs into `telegraf.conf`); the plugin
module's job stops at validating and exposing configuration.

`common.py` holds `CommonOpts`, a mixin every plugin config model
inherits, providing the options Telegraf accepts on every input/
processor/output plugin (`name_override`, `namepass`/`namedrop`,
`fieldpass`/`fielddrop`, `tagpass`/`tagdrop`, `taginclude`/`tagexclude`,
`interval`, `measurement_prefix`). It also defines `advanced_field()`,
used to mark rarely-touched fields with `json_schema_extra={"advanced":
true}` so the frontend can collapse them behind a disclosure instead of
showing everything inline.

Per-plugin config models live under `inputs/` and `outputs/` (e.g.
`inputs/mqtt.py` → `MqttConsumerConfig`, `outputs/timescaledb.py` →
`TimescaleDBOutputConfig`), one file per plugin, each a typed Pydantic
model — not a hand-written JSON Schema dict — that inherits `CommonOpts`.
`PluginRegistry` pairs each config model with metadata (name, category,
Telegraf plugin name) via a `PluginDefinition`, and derives the exposed
JSON Schema straight from `config_model.model_json_schema()`, so schema,
defaults, and validation all come from one source of truth. A `processors/`
directory should follow the same convention once processor plugins exist.

---

# Telemetry Module

telemetry/

    api.py

    models.py

    service.py

    repository.py

Responsibilities

- discover available telemetry tables (TimescaleDB hypertables)

- query recent rows from a table, with `limit`/`since`

Telemetry tables are not modeled in MongoDB — a table's existence and
schema are a side effect of how a Collector's plugins are configured
(the table name comes from `name_override` on an input, or from the
mqtt_consumer's own measurement naming). So instead of a Mongo-backed
CRUD module like the others, this module talks to TimescaleDB directly
via an `asyncpg` connection pool (see `database.get_timescale_pool`),
discovering tables from `timescaledb_information.hypertables` and
validating any user-supplied table name against that list before it is
ever interpolated into a query.

`GET /api/telemetry/tables` and `GET /api/telemetry/{table}` are the
current endpoints. The response envelope (`TelemetryQueryResult`: table,
columns, rows) is a Pydantic model, but individual row contents are
`dict[str, Any]` since the schema is dynamic by design — this is the one
place in the codebase where "every object is a model" applies to the
envelope rather than every field, because the field set genuinely isn't
known until the plugin configuration that created the table is read.

---

# AI Module

ai/

    api.py

    service.py

    prompts.py

Responsibilities

- SQL generation

- SQL explanation

Future

- dashboard generation

- collector generation

---

# Shared Module

shared/

contains reusable components.

Examples

exceptions.py

responses.py

enums.py

validators.py

utils.py

logging.py

---

# Frontend Layout

frontend/

    src/

        api/

        components/

        pages/

        hooks/

        stores/

        layouts/

        charts/

        types/

        utils/

---

# Pages

pages/

CollectorList

CollectorEditor

AutomaterList

AutomaterEditor

DashboardList

DashboardEditor

Settings

Home

---

# Components

Reusable UI only.

Examples

Button

Card

Table

Dialog

CodeEditor

PluginForm

PanelEditor

ChartPreview

---

# API Layer

Every HTTP request belongs here.

api/

collector.ts

dashboard.ts

automater.ts

ai.ts

Never make HTTP requests directly from components.

---

# Types

Contains TypeScript models.

These should mirror backend Pydantic models whenever practical.

---

# Runtime Directory

runtime/

collectors/

automater/

Generated configuration files live here.

Nothing inside runtime should be committed to Git.

---

# Plugins Directory

plugins/

telegraf/

processor/

output/

Contains source code for custom Telegraf plugins.

Examples

rule_processor/

celery_output/

Each plugin should have its own README.

---

# Examples Directory

examples/

    demo/

        seed.py

        apiary_publisher.py

        solar_publisher.py

        manufacturing_publisher.py

        main.py

        Dockerfile

        requirements.txt

        README.md

Manual verification tools and demos — not part of the application, and
not started by a plain `docker compose up`. `demo/` self-provisions 3
curated projects (one per data source kind: MQTT, HTTP, Kafka) via the
backend's own REST API, then publishes synthetic telemetry to each
forever, used to exercise the Collector -> ingestion -> TimescaleDB
pipeline end to end and to populate the public read-only demo. It's
wired into `docker-compose.yml` behind `profiles: [demo]`:

    docker compose --profile demo up -d

This `profiles` pattern is the general convention for anything that
should be buildable/runnable via compose but shouldn't come up by
default — reach for it before adding a new always-on service for
something that's really a manual/dev-only tool.

---

# Scripts

scripts/

development

build

cleanup

generate

Used for developer tooling only.

No application logic belongs here.

---

# Docker

docker/

backend/

frontend/

plugins/

Contains Dockerfiles only.

No compose files.

---

# Tests

tests/

backend/

frontend/

integration/

fixtures/

tests should mirror the source tree.

---

# Naming Conventions

Directories

lowercase

singular

collector

dashboard

plugin

Files

snake_case.py

collector_service.py

panel_models.py

Classes

PascalCase

Collector

Dashboard

RuleProcessor

Functions

snake_case

generate_config()

deploy_container()

validate_rule()

Variables

snake_case

collector_id

dashboard_name

plugin_type

Constants

UPPER_CASE

DEFAULT_TIMEOUT

DEFAULT_TOPIC

---

# API Conventions

REST endpoints

/api/collector

/api/dashboard

/api/automater

/api/plugin

Never use verbs.

Correct

POST /collector

DELETE /collector/{id}

Incorrect

/createCollector

/deleteCollector

---

# Database Rules

Mongo stores

configuration

Timescale stores

telemetry

Never mix them.

---

# Business Rules

Every domain owns

models

repository

service

api

Avoid cross-domain imports whenever possible.

Use services instead.

---

# Docker Rules

Only the backend controls Docker.

Frontend never communicates with Docker directly.

Generated configuration files should never be edited manually.

---

# Logging

Use Python logging.

Never use print().

Logs should include

timestamp

service

level

message

---

# Error Handling

Raise exceptions.

Never return None to indicate failure.

Convert exceptions into HTTP responses in the API layer.

---

# Configuration

Environment variables belong in

.env

Configuration loading belongs in

config.py

Never access os.environ directly outside config.py.

---

# Pydantic

Every object crossing an API boundary must have a Pydantic model.

Never accept arbitrary dictionaries.

---

# Mongo

Repositories return models.

Not dictionaries.

---

# Frontend

Pages own state.

Components receive props.

Avoid business logic inside components.

---

# Rule

Whenever adding a new feature ask

Which module owns this?

If the answer is unclear

the architecture is probably wrong.