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

Event

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

Represents an event detection service. Shipped shape (Milestone 5,
2026-07-10) differs from the original MVP sketch below in one structural
way: there is no `processors` field. A `Rule Processor` is synthesized
fresh at deploy time from `rules` (see `AutomaterService
._synthesize_rule_processor`), not persisted as its own plugin instance —
the domain object only ever stores what the user actually authored.

Fields

id

project_id

name

description

enabled

status

inputs

rules

outputs

schema_version

docker

created_at

updated_at

A project can have any number of Automaters (mirrors Collector, never
restricted to one per project). An Automater can have more than one mqtt
input — one per distinct table its rules target, added on demand when a
new rule needs a table the Automater doesn't already watch (see
`AutomaterService.create_rule`) — so "one Automater" no longer implies
"one table". The MVP Automater has

MQTT Input(s)

Rule Processor (synthesized, not stored)

Celery Output

---

# Rule

Represents a named set of conditions evaluated against one table. Lives
inside exactly one Automater but has its own lifecycle independent of it
(activate/deactivate/delete vs. the Automater's deploy/stop/delete).

Fields

id

name

description

category

event_type

severity

message

enabled

priority

table

conditions

identifiers

ttl

`category`/`event_type` are free text (UI grouping/filtering only, not
consumed by plugin logic). `severity` is `low` | `medium` | `high` |
`critical`. `message` is a `{field}`-interpolated template, filled in by
the Go rule processor from the matched metric's tags/fields at match
time. `table` is the measurement/hypertable this rule's conditions
evaluate against — conditions within one rule always share a table (no
cross-table correlation). `identifiers` are the tag/field names hashed
(in order) into the Redis dedup/firing-state key; `ttl` is a Go duration
string bounding how long a firing state persists between repeat matches.

There is no `operator` field on Rule — see Condition's `join` below.

---

# Condition

Represents a single comparison against one column of a Rule's `table`.

Fields

column

operator

value

join

Supported operators

>

>=

<

<=

==

!=

`join` (AND/OR) is how this condition combines with the *running result
of every condition before it* in the Rule's `conditions` list — evaluated
strictly left-to-right, no operator precedence, no parentheses ("a AND b
OR c" always means "(a AND b) OR c"). Ignored on a Rule's first
condition, since nothing precedes it to combine with. This lives on
Condition, not Rule, specifically so a Rule can express a mixed chain
like `a==1 AND b>3 OR c<5` — a single per-Rule operator (an earlier,
superseded design) could only ever be all-AND or all-OR across every
condition.

`column` matches the DB-schema vocabulary (not `metric`) — the rule
builder UI works the same way the Dashboard's schema browser does: pick
table, then column, then operator, then value. `column` may resolve
against either a tag or a field on the matched metric (evaluation checks
tag first, then field) — the UI presents both identically.

---

# Rule Processor Configuration

Synthesized at deploy time from an Automater's `rules`, not stored as its
own persisted object.

Contains

Rules

There is no `Evaluation Mode` or `Output Field` — every enabled rule on a
matching table is evaluated independently on its own merits (a single
metric can produce more than one event); the matched rule's name is
always written to a fixed tag, not a configurable one. Both were dropped
from the config surface entirely (no legal alternative value existed to
select between) rather than kept unused.

Future versions may support

window evaluation

aggregations

statistics

---

# Event

Represents one match/clear occurrence from a Rule. Written by the Celery
worker (`app/automater/tasks.py`'s `log_rule_match`) from the tags/fields
the Go rule processor already stamped onto the matched metric — not a new
data source, just persisting what was previously only logged. Stored in
Mongo, not TimescaleDB — see the Philosophy/principle #5 note and
`iotops-workspace/ROADMAP.md`'s "Events sidebar" entry for the reasoning.

Fields

id

project_id

automater_id

rule_id

rule_name

table

category

severity

event_type

message

flag

tags

fields

matched_at

created_at

`project_id`/`automater_id` come from `DeployedRule` (see Rule Processor
Configuration above) — not stored on Rule itself, since a Rule's container
is already implicit via `Automater.rules`. `rule_id` (not just `rule_name`)
is what attribution actually keys on, since Rule names aren't required
unique. `flag` is `"match"` (this occurrence just started firing) or
`"clear"` (it just stopped). `tags`/`fields` are the full snapshot of the
matched metric, for anything not already promoted to its own field.

Surfaced via a project-scoped sidebar on every Dashboard within that
project (not per-Dashboard, not a cross-project view — an Event only ever
relates to a Project, never to one specific Dashboard), live-updated via
Server-Sent Events, and summarized on the Overview page (counts per
project per rule, latest events).

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

y_axis (first series, left axis)

series (list of SeriesConfig — additional series)

legend

tooltip

zoom

theme

Bar Chart and Scatter Chart share this same shape (minus `zoom` for Bar).

---

# Series Config

Describes one additional series on a Line/Bar/Scatter chart, beyond the
chart's own `y_axis`.

Fields

field

label

axis (`left` or `right`)

type (`line` | `bar` | `scatter`, inherits the parent chart's type when unset)

Enables mixed chart types and dual y-axes on one panel (e.g. temperature as
a line on the left axis, humidity as bars on the right axis).

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

SQL may reference `$__timeFrom`/`$__timeTo` (the dashboard's selected time
range) and `$variable_name` (dashboard Variables) — substituted server-side
before execution.

---

# Variable

Fully schema-driven — no free-typed text/number/options, no hand-written or
AI-written SQL. A Variable is defined by picking a value column (and,
optionally, a predicate column in the same table) from the schema browser.

Fields

name

label

table

value_column

predicate_column (optional — must belong to `table`)

predicate_variable (optional — name of an earlier Variable in the Dashboard's
`variables` list; required together with `predicate_column`)

The options list a Variable offers is always derived, never stored: the
backend builds `SELECT DISTINCT value_column FROM table [WHERE
predicate_column = $predicate_variable]` (see `build_variable_source_sql` in
`dashboard/models.py`) and runs it through the same substitution pipeline as
panel queries. Variables may be referenced inside panel SQL as `$name`. A
Variable's `predicate_variable` may only reference a Variable defined earlier
in the list (enforced by `validate_variables`), producing Grafana-style
chained/cascading variables (e.g. Project narrows Device) without a
dependency graph — list order is the dependency order.

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

Event

Variables

---

# Relationships

Collector

references

Project

Dashboard

references

Project

Event

references

Project, Automater, Rule (by id, same as Collector/Dashboard -- no
cascading delete)

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

Automaters own Rules — structurally (a Rule lives in `Automater.rules`,
never independently persisted), though Rule still has its own lifecycle
(activate/deactivate/delete) distinct from the Automater's own
(deploy/stop/delete).

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

An Automater must contain at least one Rule; a Rule must contain at
least one Condition. Rule names are deliberately *not* required unique
(within an Automater or globally) — the Redis firing-state key is keyed
on Rule `id`, not `name`, precisely so two same-named rules never
collide.

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