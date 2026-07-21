# IoTOps

Self-hosted IoT Operations Platform — visually configure telemetry
collection, automate event-driven workflows, and build dashboards without
hand-writing Telegraf configuration files.

## Features

- **Data Ingestion (Collectors)** — build an MQTT/HTTP/Kafka/AMQP input
  visually; generates Telegraf TOML and deploys it as a Docker container
- **Automation (real-time Rules)** — AND/OR condition rules evaluated per
  message, with Redis-backed dedup and Celery-based event publishing
- **Scheduled Rules (Query Rules)** — SQL checks on a timer for
  cross-table/cross-metric correlation a stream processor can't express
- **Dashboards** — drag-resizable Panels, a Variable Builder, event
  overlays on charts, and an AI-assisted SQL builder
- **Events** — every Rule match/clear persisted and streamed live into a
  searchable sidebar available from any page
- **AI Co-pilot** — a chat panel grounded in real tool-calling (not
  context-stuffing) over live telemetry and events; answers data
  questions, and proposes new Rules, dashboard panels, or whole
  dashboards as reviewable, prefilled drafts — never auto-created. Runs
  on Anthropic Claude or, as a free-tier default, Google Gemini. The
  Dashboard's own AI-assisted SQL builder is a separate, simpler feature
  and predates the Co-pilot.

## Tech Stack

FastAPI · Pydantic · React · TypeScript · Vite · TimescaleDB · MongoDB ·
Redis · Celery · Docker · Anthropic Claude / Google Gemini ·
[custom-telegraf](https://github.com/ridvanzengin/custom-telegraf)

## Prerequisites

- Docker and Docker Compose
- The backend talks to the host Docker daemon (via a mounted
  `docker.sock`) to deploy Collector/Automater containers, so
  `HOST_RUNTIME_DIR` in `.env` must be set to this repo's `runtime/`
  directory as an absolute host path
- Optional, for AI features: a free [Gemini](https://aistudio.google.com/apikey)
  API key (default), or an [Anthropic](https://www.anthropic.com) API key
  (set `AI_PROVIDER=anthropic`)

## Quickstart

```bash
cp .env.example .env   # set HOST_RUNTIME_DIR (and GEMINI_API_KEY or ANTHROPIC_API_KEY if using AI features)
docker compose up
```

- Backend: http://localhost:8000/health
- Frontend: http://localhost:5173
- In-app documentation: http://localhost:5173/docs

## Documentation

- **In-app docs** — once the stack is running, open
  http://localhost:5173/docs for features, technical overview, and
  known limitations, written for users of a running instance
- [CLAUDE.md](CLAUDE.md) — architecture and conventions for contributors
- [docs/](docs/) — full design docs: vision, architecture, domain
  models, repository structure, and the phased development plan
- [CHANGELOG.md](CHANGELOG.md) — dated history of what's shipped

## Testing

```bash
.venv/bin/python -m pytest tests/backend/ -q
```

## Related

- [custom-telegraf](https://github.com/ridvanzengin/custom-telegraf) —
  the custom Telegraf build bundling this project's Automation Engine
  plugins (`processors/rule`, `outputs/celery`).

## Contributing

Issues and pull requests are welcome. For anything non-trivial, please
open an issue first to discuss the change — see
[docs/development-plan.md](docs/development-plan.md) for what's already
planned or in flight.

## License

MIT — see [LICENSE](LICENSE).
