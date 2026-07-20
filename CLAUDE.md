# IoTOps

Self-hosted IoT Operations Platform. Users visually configure telemetry
collection, automate event-driven workflows, and build dashboards without
hand-writing Telegraf configuration files. Domain-agnostic core (first
showcase: smart beekeeping).

**Status:** v1 (Milestones 0–4: Collector, telemetry pipeline, Dashboard
system, Beekeeping showcase) is shipped. Milestone 5 (Automation Engine,
v1.1) has its core engine done — real rule/Redis/Celery logic in both
custom-telegraf plugins, Automater backend + frontend, automated tests,
and a persisted Events feature (Mongo-backed, SSE-delivered sidebar with
activity-bar redesign, Panel-chart overlays) — with the beekeeping
swarm-alert wiring still open. Milestone 6 (AI Assistant, v1.2) has the
Co-pilot's Q&A slice and rule-suggestion slice (Slices 1–2) shipped —
real Anthropic tool-calling, a suggestion always available in every
conversation (not gated behind a specific entry point), never
auto-creating anything. See
[docs/development-plan.md](docs/development-plan.md) for current
milestone status.

**Roadmap is phased for a fast v1 ship:** v1 = Collector + Telemetry +
Dashboard + Beekeeping showcase (no automation, no AI). Automation Engine
(v1.1) and AI Assistant (v1.2) are fast-follows, not blockers. Beekeeping is
just the first showcase — more domain showcases are planned post-v1. See
[docs/development-plan.md](docs/development-plan.md).

## Stack

- Backend: FastAPI (Python), Pydantic models as the canonical domain
  representation
- Frontend: React + TypeScript + Vite
- Telemetry storage: TimescaleDB
- Config storage: MongoDB
- Messaging: MQTT broker (Mosquitto) + Redis (Celery broker)
- Runtime: Docker containers running Telegraf (Collector + Automater
  services)
- Async tasks: Celery workers
- AI: Anthropic API (Claude) for both SQL generation and the Co-pilot chat

## Core principles

1. **Everything is a model.** Every domain object is a Pydantic model; UI,
   API, Docker configs, and DB documents are all derived from it. Never
   hand-edit generated TOML.
2. **Infrastructure is an implementation detail.** Users interact with
   Collectors/Dashboards/Rules, not Telegraf/ECharts/processor plugins.
3. **Configuration over code.** Features are built via forms, plugins, and
   templates, not by writing new application code.
4. **Domain-organized repo**, not layer-organized — see
   [docs/repository-structure.md](docs/repository-structure.md).
5. **Mongo stores configuration and discrete structured records (e.g.
   Events); TimescaleDB stores continuous numeric telemetry.** Never mix
   the two. An Event (a Rule match/clear occurrence) is variably-shaped
   and inherently low-volume (match/clear + TTL dedup already collapses
   it to meaningful transitions, not per-tick data) — Mongo's document
   queries fit it, not TimescaleDB's fixed-hypertable-columns/range-
   aggregation model. See CHANGELOG.md's 2026-07-10 "Events sidebar +
   persisted event store" entry for the full reasoning.

## Docs

Read the relevant doc before working in that area:

- [docs/vision.md](docs/vision.md) — product vision, scope, non-goals
- [docs/architecture.md](docs/architecture.md) — services, data flow,
  lifecycle diagrams
- [docs/domain-models.md](docs/domain-models.md) — Pydantic entities and
  their fields/relationships
- [docs/repository-structure.md](docs/repository-structure.md) — directory
  layout and naming conventions
- [docs/development-plan.md](docs/development-plan.md) — phased roadmap
  (v1/v1.1/v1.2), milestones, and current build order

## Conventions (see repository-structure.md for full detail)

- Python: snake_case files/functions, PascalCase classes, structured
  `logging` module (never `print`)
- REST: nouns only (`POST /collector`, not `/createCollector`)
- Every object crossing an API boundary is a Pydantic model — never a raw
  dict
- Raise exceptions instead of returning `None` on failure; convert to HTTP
  responses at the API layer
