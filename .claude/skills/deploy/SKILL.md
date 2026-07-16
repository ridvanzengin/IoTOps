---
name: deploy
description: Deploy IoTOps to production (https://iotops.online) on the shared Hetzner VM "ringo" — routine updates, fresh-server setup, or health-checking/troubleshooting the live deployment. Use whenever asked to deploy, redeploy, ship to production, update the live site, or check on iotops.online's health.
---

IoTOps runs in production on the same Hetzner VM as AgriTwin, reusing its
shared `infra` Compose project (nginx, TimescaleDB, Redis) rather than
running its own — see `deploy/SERVER_SETUP.md` for full topology and the
first-time setup walkthrough, and the deployment plan history in
`docs/development-plan.md`'s Portfolio Demo Deployment section. This
skill assumes that initial setup is done (it is, as of 2026-07-16) and
covers *operating* the live deployment: routine updates, and the
debugging playbook for the failure modes actually hit standing this up.

SSH: `ssh -i ~/.ssh/id_ed25519_personal root@167.233.143.105`. Every
command below runs on that VM unless noted otherwise.

## Routine update (the common case)

```bash
bash /opt/iotops/deploy/scripts/deploy.sh
```

Pulls `main` (or whatever branch is checked out — check first if you're
mid-feature-branch), rebuilds images, restarts app services, and only
touches the shared nginx if `deploy/nginx/iotops.conf` actually changed
(gated by `nginx -t`, never reloads on a routine unrelated push). Does
**not** touch `custom-telegraf` — if that repo changed, rebuild it
separately:

```bash
cd /opt/custom-telegraf && git pull origin main && docker build -t custom-telegraf:latest .
```

Restart just the affected service(s) after a targeted fix instead of the
whole stack where possible:

```bash
cd /opt/iotops
docker compose -p iotops --env-file deploy/iotops/.env.prod -f deploy/iotops/docker-compose.prod.yml build <service>
docker compose -p iotops --env-file deploy/iotops/.env.prod -f deploy/iotops/docker-compose.prod.yml up -d --no-deps <service>
```

## Fresh server / disaster recovery

Follow `deploy/SERVER_SETUP.md` top to bottom — it's the authoritative,
numbered playbook (DNS → clone → build custom-telegraf → secrets →
nginx vhost → DB → build+start → verify → DNS wait → TLS → systemd).
Don't improvise a different order; the numbering encodes real
dependencies (e.g. the DB must exist before the backend can start
cleanly, custom-telegraf must be built before the demo seeder tries to
deploy an Automater).

## Verifying a deployment actually worked

Don't stop at "containers are Up" — that told us nothing the day this
was first stood up. Check, in order:

```bash
# Public reachability (both protocols)
curl -sI https://iotops.online/ | head -3
curl -s https://iotops.online/api/collector | head -c 300

# AgriTwin unaffected -- check this after ANY shared-nginx touch
curl -sI https://agritwin.online/ | head -3

# Container health -- names, not just count
docker ps -a --format 'table {{.Names}}\t{{.Status}}' | grep iotops

# Telemetry actually landing, not just "container started"
PASS=$(grep IOTOPS_DB_PASSWORD /opt/iotops/deploy/iotops/.env.prod | cut -d= -f2)
docker exec infra-db-1 psql "postgresql://iotops:$PASS@localhost:5432/iotops" -c '\dt'
docker exec infra-db-1 psql "postgresql://iotops:$PASS@localhost:5432/iotops" -c 'SELECT count(*), max(time) FROM hive_environment;'

# Automater/Collector container count should match Mongo's automaters
# collection count exactly (1:1) -- if Mongo has more, something is
# retrying-and-duplicating again (see "Automater duplication" below)
docker exec iotops-mongo-1 mongosh --quiet iotops --eval 'db.automaters.countDocuments()'
docker ps -a --filter 'name=iotops-automater' --format '{{.Names}}' | wc -l
```

Manufacturing/Kafka containers (`iotops-collector-manufacturing-*`,
`iotops-automater-manufacturing-*`) are *expected* to crash-loop — Kafka
is deliberately not deployed. Don't chase that as a bug.

## Known failure modes (all hit for real standing this up)

**Shared `infra-nginx-1` silently stops listening on 80/443** (master +
worker processes alive per `docker exec infra-nginx-1 ps aux`, but
`docker exec infra-nginx-1 ss -tlnp` shows nothing bound) after several
new containers join `infra_proxy` in quick succession. `nginx -s reload`
does *not* fix this — it needs an actual restart:
```bash
docker exec infra-nginx-1 ss -tlnp   # confirm: nothing on 80/443 despite ps showing workers
docker restart infra-nginx-1
docker exec infra-nginx-1 ss -tlnp   # confirm: now listening
curl -sI https://agritwin.online/    # confirm AgriTwin recovered too -- this affects both apps
```
This is a shared-infra action — get explicit confirmation before running
`docker restart infra-nginx-1`, naming it exactly, every time.

**502 after any deploy that recreates `backend`/`frontend`**: check
`deploy/nginx/iotops.conf`'s `proxy_pass` targets are the `set $upstream
http://...; proxy_pass $upstream;` form, never a bare static `proxy_pass
http://host:port;`. A static hostname is resolved once at nginx
startup/reload and cached indefinitely — the `resolver ... valid=30s`
directive only actually takes effect through the variable form. Every
`docker compose up` that recreates a container gives it a new IP, so a
bare `proxy_pass` silently 502s until the next manual `nginx -s reload`.
This bit the very deploy that added Kafka (recreated `frontend`).
Diagnose with:
```bash
docker logs infra-nginx-1 --tail 20 | grep error   # shows the stale IP nginx is stuck on
docker inspect iotops-frontend-1 --format '{{.NetworkSettings.Networks.infra_proxy.IPAddress}}'  # actual current IP
```
If they differ and the vhost still uses bare `proxy_pass`, fix
`iotops.conf` (should already be fixed as of 2026-07-16) rather than just
reloading nginx as a one-off patch — a reload masks this deploy's
symptom but the config would still break on the *next* one.

**`infra-db-1` connection exhaustion** (`TooManyConnectionsError:
remaining connection slots are reserved for roles with the SUPERUSER
attribute`). `max_connections=25` total, shared with AgriTwin (~13 in
steady use), leaving ~9-12 for IoTOps. asyncpg's own default pool
(`min_size=10, max_size=10`) is too large for this — `app/database.py`
and `app/query_rule/tasks.py` already cap their pools small (5 and 3).
If a *new* asyncpg pool gets added anywhere, size it explicitly, don't
take the library default. Check current usage:
```bash
docker exec infra-db-1 psql -U postgres -c "SELECT count(*), usename FROM pg_stat_activity GROUP BY usename;"
```

**Automater duplication on failed deploy** (already fixed at the root in
`AutomaterService.create_rule` — it rolls back a just-created Automater
and defers Collector `http_forward` wiring until deploy actually
succeeds). If it ever recurs (a new code path with the same
persist-before-deploy shape), the symptom is `automaters` collection
count exceeding actual running `iotops-automater-*` containers, and a
Collector's Telegraf config showing `outputs: http (Nx) ...` where N is
suspiciously large. Cross-check which Automater a Dashboard/QueryRule
actually references (`event_rule_ids` on dashboard panels) before
deleting anything — that's the one to keep.

**`custom-telegraf:latest` missing** → any Automater deploy 404s
(`ImageNotFound`). Build it (see Routine update section above) *before*
anything tries to deploy an Automater, not after — a client retrying a
failed create against a missing image is exactly what triggers the
duplication failure mode above.

## Safety rules (non-negotiable, not just style)

- `infra-nginx-1`, `infra-db-1`, `infra-redis-1` are **shared with
  AgriTwin, live**. Any direct mutation (restart, exec into to run
  scripts, raw Mongo/Postgres deletes) needs explicit confirmation naming
  the exact action — a general "yes" or "go ahead" earlier in the
  conversation does not carry forward to a new specific risky action.
- `nginx -t` gates every `nginx -s reload`, no exceptions. Check
  `agritwin.online` before and after any shared-nginx touch.
- Prefer read-only diagnosis (`docker ps`, `docker logs`, `psql SELECT`,
  `mongosh countDocuments`) before any write/restart/delete — establish
  what's actually broken before acting on it.
- HTTPS vhost changes: edit `deploy/nginx/iotops.conf` in the repo (never
  edit the VM's copy directly), commit, then copy over per
  `SERVER_SETUP.md`/`deploy.sh`'s pattern.
