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

**Acceptance Criteria**

- Publishing MQTT messages stores rows in TimescaleDB.
- API can query recent telemetry.

---

## Milestone 3 — Dashboard System

### Objective

Visualize telemetry.

### Tasks

- Implement Dashboard models.
- Implement Panel models.
- Implement chart models.
- Create dashboard CRUD API.
- Build dashboard editor UI.
- Integrate Apache ECharts.
- Add line chart.
- Add bar chart.
- Add gauge chart.

**Acceptance Criteria**

- User can create a dashboard.
- User can add panels.
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
