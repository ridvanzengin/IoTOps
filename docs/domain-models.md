# Domain Model

Version: 0.1.0

---

# Philosophy

Everything inside IoTOps is represented by a Pydantic model.

Models are the canonical representation of the platform.

MongoDB stores serialized models.

Telegraf configuration is generated from models.

The frontend UI is generated from models.

---

# Root Entities

The MVP contains the following root entities.

Project

Collector

Automater

Dashboard

Plugin

Rule

Template (future)

Datasource (future)

---

# Project

Represents a grouping of a Collector with its Automaters and Dashboards.

Fields

id

name

description

created_at

updated_at

schema_version

Project is intentionally lightweight — an organizational grouping only, not
an access-control or tenancy construct. It does not scope or filter which
telemetry tables a Dashboard's panels can query; the schema browser and
query builder always see every TimescaleDB table globally, regardless of
project. There is no collector-to-table-to-project lineage tracking.

---

# Collector

Represents a telemetry collection service.

Fields

id

project_id

name

description

enabled

status

inputs

processors

outputs

docker

created_at

updated_at

A Collector owns

- Inputs

- Processors

- Outputs

---

# Collector Status

Possible values

CREATED

STOPPED

STARTING

RUNNING

UNHEALTHY

STOPPING

ERROR

---

# Input Plugin

Represents a telemetry source.

Fields

id

plugin_type

name

enabled

configuration

Examples

MQTT

HTTP

Modbus (future)

OPC-UA (future)

---

# Processor Plugin

Processes telemetry.

Fields

id

plugin_type

enabled

configuration

Examples

Rule Processor

Converter

Math

Filter

Future processors may be added without changing Collector.

---

# Output Plugin

Represents telemetry destinations.

Fields

id

plugin_type

enabled

configuration

Examples

TimescaleDB

InfluxDB (future)

Prometheus (future)

File (future)

---

# Plugin Configuration Models

`configuration` on an Input/Processor/Output Plugin is not an arbitrary
dict. It is validated against a typed Pydantic model chosen by
`plugin_type` (e.g. `MqttConsumerConfig` for `"mqtt"`,
`TimescaleDBOutputConfig` for `"timescaledb"`) — one file per plugin, not
a hand-written JSON Schema. See
[repository-structure.md](repository-structure.md) for where these live.

Every such model inherits `CommonOpts`, the options Telegraf accepts on
any input/processor/output plugin: `name_override`/`name_prefix`/
`name_suffix`/`alias`, `namepass`/`namedrop`, `fieldpass`/`fielddrop`,
`tagpass`/`tagdrop`, `taginclude`/`tagexclude`, `interval`,
`measurement_prefix`.

Fields are split into primary and advanced. Advanced fields (most of
`CommonOpts`, plus rarely-touched plugin-specific fields like TLS/auth
settings) are marked in the model via `json_schema_extra={"advanced":
true}`; the frontend's schema-driven form renders primary fields inline
and collapses advanced ones behind a disclosure. This grouping is
metadata on the model, not something the frontend hardcodes per plugin —
adding a new plugin only means writing its config model, the form
appears automatically.

Every field that has a real, meaningful default (as opposed to `None`)
declares it with `Field(default=...)` rather than `default_factory`,
because only static defaults are surfaced in `model_json_schema()` — this
is how the UI's "preloaded with sensible defaults" behavior works, and
why `default_factory` should be avoided for anything the form should
prefill.

---

# Automater

Represents an event detection service.

Fields

id

name

description

enabled

status

inputs

processors

outputs

created_at

updated_at

The MVP Automater should have

MQTT Input

Rule Processor

Celery Output

---

# Rule

Represents a logical condition.

Fields

id

name

description

enabled

operator

conditions

priority

---

# Rule Operator

Supported

AND

OR

---

# Condition

Represents a single comparison.

Fields

metric

operator

value

Supported operators

>

>=

<

<=

==

!=

---

# Rule Processor Configuration

Contains

Rules

Evaluation Mode

Output Field

Future versions may support

window evaluation

aggregations

statistics

---

# Dashboard

Fields

id

project_id

name

description

variables

panels

layout

created_at

updated_at

`layout` and `Panel.position` are not competing layout concepts:
`Panel.position` (x/y/width/height) is the authoritative per-panel grid
rect, what the frontend's grid system needs per panel. `layout` is a thin,
loosely-typed container for grid-wide settings that aren't per-panel (e.g.
column count, row height) — not a duplicate of per-panel positions.

---

# Panel

Fields

id

title

chart

query

time_range

refresh_interval

position

Each Dashboard contains many Panels.

---

# Panel Position

Contains

x

y

width

height

Used by the frontend grid system.

---

# Chart

Base class.

Derived classes

LineChart

BarChart

ScatterChart

PieChart

GaugeChart

Future

Heatmap

Histogram

BoxPlot

---

# Line Chart

Fields

title

x_axis

y_axis

series

legend

tooltip

zoom

theme

---

# Query

Represents SQL.

Fields

sql

variables

limit

timezone

The frontend never edits database objects directly.

Only Query objects.

---

# Variable

Fields

name

label

default

type

options

Variables may be referenced inside SQL.

---

# Docker Configuration

Represents deployment information.

Fields

image

container_name

network

restart_policy

volumes

environment

This object is generated.

Users should rarely edit it.

---

# Plugin

Represents available plugin types, as exposed over the API
(`GET /api/plugin`, `GET /api/plugin/{plugin_type}`).

Fields

id

name

category

telegraf_name

version

description

configuration_schema

supported_platforms

`configuration_schema` is derived, not hand-written — it's
`config_model.model_json_schema()` for the plugin's actual Pydantic
config model (see Plugin Configuration Models above). `telegraf_name` is
the real Telegraf plugin name (e.g. `mqtt_consumer`, `postgresql`), which
may differ from IoTOps' own `name` (`mqtt`, `timescaledb`) — the
generator uses `telegraf_name` to build the `[[inputs.X]]` / `[[outputs.X]]`
TOML table names.

---

# Plugin Categories

Input

Processor

Output

---

# Plugin Registry

The backend maintains a registry.

Example

MQTT

↓

Input Plugin

↓

Schema

↓

Configuration Form

↓

Validation

↓

Generator

The UI should never hardcode plugin forms.

---

# Runtime Objects

Not stored permanently.

Examples

Generated TOML

Container IDs

Health Status

Runtime Logs

Telemetry Query Result

These belong to runtime services.

---

# Telemetry Query Result

Represents the response from querying a telemetry table
(`GET /api/telemetry/{table}`). Not a persistent object, and not backed
by Mongo — telemetry tables live only in TimescaleDB and are discovered
dynamically (see [repository-structure.md](repository-structure.md)'s
Telemetry Module section).

Fields

table

columns

rows

`rows` is `list[dict[str, Any]]` — the one place the field set is
genuinely dynamic, since it mirrors whatever columns a Collector's
plugin configuration happened to create. The envelope (this model) is
still a Pydantic model; the row *contents* are the exception to
"everything is a model," not the response as a whole.

---

# Persistent Objects

Project

Collector

Automater

Dashboard

Panel

Plugin Metadata

Rule

Variables

---

# Relationships

Collector

references

Project

Dashboard

references

Project

Collector

contains

Input Plugins

Processor Plugins

Output Plugins

Dashboard

contains

Panels

Panel

contains

Query

Chart

Layout

Automater

contains

Rules

Rules

contain

Conditions

---

# Ownership

Projects do not own Collectors or Dashboards — they only reference a
Project by `project_id`. Deleting a Project does not cascade: Collectors
and Dashboards that referenced it simply keep a `project_id` that no
longer resolves to anything.

Collectors own Inputs.

Collectors own Outputs.

Collectors own Processors.

Dashboards own Panels.

Panels own Queries.

Automaters own Rules.

Rules own Conditions.

---

# Validation Rules

Every model validates itself.

Examples

A Collector must contain at least

one Input

and

one Output.

Dashboard names must be unique.

Rule names must be unique inside an Automater.

Panel positions cannot overlap.

Plugin configuration must match its schema.

---

# Serialization

All persistent objects must support

JSON serialization

JSON deserialization

Version migration

No object should require manual parsing.

---

# Versioning

Every root entity contains

schema_version

Future migrations operate on schema versions.

Never rely on application version.

---

# Identity

Every root entity uses UUID.

Human-readable names are not identifiers.

---

# Future Models

Analytics Job

ML Model

Prediction

Notification

Workspace

Organization

Remote Agent

Device

Template

These are intentionally omitted from the MVP.