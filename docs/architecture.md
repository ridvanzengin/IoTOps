# IoTOps Architecture

Version: 0.1.0

---

# Overview

IoTOps is built as a collection of loosely coupled services.

The system intentionally separates:

- telemetry collection
- event processing
- visualization
- configuration management

This separation allows each subsystem to evolve independently.

---

# High Level Architecture

                     +----------------+
                     |   Web Browser  |
                     +--------+-------+
                              |
                         REST API
                              |
                     +--------v--------+
                     |     FastAPI     |
                     +--------+--------+
                              |
              +---------------+----------------+
              |               |                |
              |               |                |
              v               v                v
          MongoDB       Docker Engine     TimescaleDB
              |                                ^
              |                                |
              |                                |
              +------------+-------------------+
                           |
                    MQTT Broker
                     /       \
                    /         \
                   /           \
                  v             v
      Collector Telegraf   Automater Telegraf
             |                    |
             |                    |
             |            Celery Output Plugin
             |                    |
             |                    v
             |               Redis Broker
             |                    |
             |                    v
             |              Celery Workers
             |
             +------------------------------+
                                            |
                                   Historical Data

---

# Runtime Services

The MVP consists of the following services.

## FastAPI

Responsibilities

- REST API
- configuration management
- dashboard management
- collector lifecycle
- automater lifecycle
- Docker orchestration
- telemetry querying
- AI endpoints

FastAPI never collects telemetry itself.

---

## MongoDB

Stores platform configuration, plus discrete structured records that
aren't continuous numeric telemetry.

Examples

- collectors
- dashboards
- rules
- templates
- plugin configurations
- events (Rule match/clear occurrences — variably-shaped, inherently
  low-volume thanks to match/clear + TTL dedup, and queried like a feed
  (recent-first, filter, paginate) rather than range-aggregated, so this
  fits Mongo's document model, not TimescaleDB's)

MongoDB is the source of truth.

---

## TimescaleDB

Stores telemetry only.

No application configuration belongs here.

Examples

- temperatures
- humidity
- vibration
- pressure
- bee hive weight

---

## Telemetry Service

The `telemetry` FastAPI module reads TimescaleDB directly via an
`asyncpg` connection pool — the only place in the backend that queries
Timescale itself, as opposed to Telegraf writing to it. It discovers
available tables from `timescaledb_information.hypertables` rather than
from any Mongo-stored model, since a table's existence is a side effect
of Collector plugin configuration, not a first-class stored object.

This sits ahead of the Dashboard/Visualizer component in the data
flow below — Dashboards query telemetry through this API rather
than talking to TimescaleDB directly, via two additional endpoints beyond
the original recent-rows query:

`GET /api/telemetry/schema` exposes table/column/type information (scoped
to real hypertables only, not internal Postgres/Timescale catalog tables)
for the Panel builder's read-only schema browser.

`POST /api/telemetry/query` executes an arbitrary, guarded read-only SQL
statement — this is what a Panel's stored `Query.sql` (see
[domain-models.md](domain-models.md#query)) actually runs through. The
service layer rejects anything that isn't a single SELECT statement before
it reaches the database.

---

## MQTT Broker

Acts as the telemetry backbone.

Collector and Automater subscribe independently.

The MQTT broker should never know about dashboards or rules.

---

## Collector Service

A Docker container running Telegraf.

Responsibilities

- subscribe to MQTT
- optional lightweight processing
- write metrics to TimescaleDB

The Collector never performs automation.

---

## Automater Service

Another Docker container running Telegraf. One Automater can subscribe to
more than one MQTT input if its rules target more than one table — it's
one deployed container per Automater, not one per table.

Responsibilities

- subscribe to MQTT
- evaluate rule processor
- send matching events through Celery Output Plugin

The Automater never writes telemetry.

---

## Redis

Message broker for Celery.

Only event notifications pass through Redis.

Telemetry never passes through Redis.

---

## Celery Workers

Responsible for executing actions.

Examples

- send email

- webhook

- MQTT publish

- logging

Future versions may include additional actions.

---

# Separation of Responsibilities

Collector

Responsible for:

✓ telemetry collection

✓ protocol conversion

✓ database writing

Not responsible for:

✗ notifications

✗ automation

✗ dashboards

---

Automater

Responsible for:

✓ evaluating rules

✓ publishing events

Not responsible for:

✗ storing telemetry

✗ dashboards

✗ visualization

---

Visualizer

Responsible for:

✓ querying TimescaleDB

✓ displaying charts

✓ dashboard editing

Not responsible for:

✗ collecting data

✗ rule evaluation

---

# Data Flow

Telemetry follows this path.

IoT Device

↓

MQTT Broker

↓

Collector

↓

TimescaleDB

↓

Telemetry Query API

↓

Dashboard

Automation follows another path.

IoT Device

↓

MQTT Broker

↓

Automater

↓

Rule Processor Plugin

↓

Celery Output Plugin

↓

Redis

↓

Celery Worker

↓

Action

The two pipelines are intentionally independent.

---

# Why Two Telegraf Instances?

Collector and Automater have different responsibilities.

Advantages

- independent deployment
- different update schedules
- isolated failures
- simpler configuration
- easier debugging

Collector failure does not stop automation.

Automation failure does not stop data collection.

---

# Configuration Lifecycle

The platform never edits TOML directly.

The workflow is:

User

↓

REST API

↓

Pydantic Models

↓

Validation

↓

MongoDB

↓

TOML Generator

↓

Docker Container

Generated configuration files are disposable artifacts.

The canonical representation is always the Pydantic model stored in MongoDB.

---

# Docker Lifecycle

Creating a Collector

1.

User submits Collector.

↓

2.

FastAPI validates the request.

↓

3.

Collector document stored in MongoDB.

↓

4.

Generate telegraf.conf

↓

5.

Create Docker container.

↓

6.

Start container.

↓

7.

Health check.

↓

8.

Status = Running

---

Stopping a Collector

User

↓

Stop

↓

Docker stop

↓

Update status

No configuration is deleted.

---

Deleting a Collector

Stop container.

Delete container.

Delete generated configuration.

Delete Mongo document.

---

# Collector Directory

Generated runtime files should not be stored in the source tree.

Example

/runtime

    /collectors

        collector-id

            telegraf.conf

    /automater

        automater-id

            telegraf.conf

Everything inside runtime is disposable.

---

# Plugin Architecture

Plugins are represented as models.

Example

MQTT Input

↓

Pydantic Model

↓

Validated Configuration

↓

TOML

↓

Telegraf

The backend never manipulates raw TOML.

---

Plugin Categories

Input

Processor

Output

Aggregator (future)

Parser (future)

Serializer (future)

---

# Dashboard Architecture

Dashboard

contains

Panels

Each panel contains

- query

- chart

- layout

- variables

- options

The frontend renders dashboards dynamically.

No dashboard code should be hardcoded.

---

# Query Architecture

Panel

↓

SQL Query

↓

TimescaleDB

↓

Result Set

↓

Chart Transformer

↓

ECharts Configuration

↓

Browser

The frontend should never receive raw Timescale objects.

Only JSON datasets.

---

# AI Integration

One AI backend at a time for every AI feature (SQL generation and the
Co-pilot chat alike) -- there used to be a separate local Ollama instance
for SQL generation specifically, retired in favor of a single interface
(`ChatProvider`, `app/ai/chat_provider.py`) that both go through. Two
implementations, picked by `Settings.ai_provider`: Anthropic
(`claude-haiku-4-5`, the user's own key) and Gemini (`gemini-2.0-flash`
by default, a free-tier alternative for when the Anthropic budget runs
out) -- `AiService` and its tool-calling loop don't know or care which is
active.

- **`POST /api/ai/sql`** and **`POST /api/ai/query-rule-sql`** —
  implemented. Ground the prompt with the live telemetry schema and
  enforce that the response is a single read-only SELECT statement before
  returning it to the caller.
- **`POST /api/ai/copilot`** — implemented. A real tool-calling conversation (`AiService.
  answer_copilot_question`), not a single-shot prompt: the model calls
  `query_occurrences`/`query_telemetry` on demand rather than having
  context pre-fetched, and answers only from tool results.

Not yet implemented (still future work, per the AI Assistant milestone —
see
[development-plan.md](development-plan.md#future--suggested-dashboards--automations)
for the full design, decided 2026-07-17): **rule and panel/dashboard
suggestions extend the Co-pilot's tool-calling loop** with three new
tools (`suggest_automation`, `suggest_panel`, `suggest_dashboard`) rather
than being separate `POST /api/ai/dashboard`/`POST /api/ai/automation`
endpoints as originally sketched here. All three "Suggest..." entry
points open the Co-pilot chat (with an intent) instead of navigating
straight to a prefilled form, since the interesting part is the
conversational back-and-forth ("do you have something in mind, or should
I suggest one?"), not generation itself. `POST /api/ai/explain` and
`POST /api/ai/collector` remain unplanned beyond being named here.

AI never directly modifies stored objects.

Generated output must always be reviewed by the user.

---

# Error Handling

Failures should be isolated.

Collector crashes

↓

Collector marked unhealthy.

↓

Automation continues.

Automation crashes

↓

Collector continues.

MongoDB unavailable

↓

Reject configuration updates.

Running collectors continue operating.

Timescale unavailable

↓

Collector retries.

↓

No dashboard queries available.

---

# Logging

Each service should have structured logs.

Required fields

timestamp

service

level

message

Optional

collector_id

dashboard_id

rule_id

plugin

device

Never use print statements.

Always use Python logging.

---

# Health Checks

Each service exposes

/health

Collector status

Automater status

Database status

MQTT connectivity

Redis connectivity

Health endpoints should be lightweight.

---

# Future Expansion

The architecture intentionally allows future additions.

Examples

Analytics Service

Machine Learning

Anomaly Detection

Remote Agents

User Management

Organizations

Template Marketplace

None of these additions should require redesigning the existing Collector or Automater modules.

---

# Architectural Rule

The platform owns the domain model.

Telegraf is only one runtime implementation.

Docker is only one deployment implementation.

MongoDB is only one persistence implementation.

Internal technologies may change.

The domain model should remain stable.