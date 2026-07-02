# IoTOps

Self-hosted IoT Operations Platform — visually configure telemetry
collection, automate event-driven workflows, and build dashboards without
hand-writing Telegraf configuration files.

See [CLAUDE.md](CLAUDE.md) for architecture and conventions, and
[docs/](docs/) for the full design docs and roadmap.

## Quickstart

```bash
cp .env.example .env
docker compose up
```

- Backend: http://localhost:8000/health
- Frontend: http://localhost:5173
