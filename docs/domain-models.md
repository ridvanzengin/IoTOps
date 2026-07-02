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

Collector

Automater

Dashboard

Plugin

Rule

Template (future)

Datasource (future)

---

# Collector

Represents a telemetry collection service.

Fields

id

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

name

description

variables

panels

layout

created_at

updated_at

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

Represents available plugin types.

Fields

id

name

category

version

description

schema

supported_platforms

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

These belong to runtime services.

---

# Persistent Objects

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