# Server Setup — Fresh Clone

Use this when setting up IoTOps on the shared VM for the first time.
For routine code updates on an already-running server, see
[Deploying Updates](#deploying-updates) below.

This deployment reuses the shared VM's existing `infra` Compose project
(nginx, TimescaleDB, Redis) that already runs AgriTwin — see
`~/personal/agritwin/deploy/infra/docker-compose.yml` on the VM at
`/opt/agritwin/deploy/infra/`. IoTOps never runs its own nginx/Postgres/
Redis in production. **Prerequisite: the `infra` project and
`agritwin-infra.service` must already be running before step 6 below.**

---

## 1 — Point DNS at the VM

In Namecheap, point `iotops.online` and `www.iotops.online` A records at
the VM's IP. Do this first — propagation takes time and nothing below
except step 10 (TLS) depends on it.

---

## 2 — Clone the repo

```bash
mkdir -p /opt/iotops-data/{mongo,mosquitto,runtime}
git clone -b main https://github.com/ridvanzengin/IoTOps.git /opt/iotops
```

---

## 3 — Clone and build `custom-telegraf`

The Automater's real-time Rules only ever consume this as a pre-built
local Docker image, tagged `custom-telegraf:latest` (matching
`settings.automater_telegraf_image`'s default) — nothing here `docker
pull`s it, so it must be built on this VM before the demo-showcase seed
step (step 7) ever tries to deploy an Automater. Skipping this step
doesn't fail loudly: the first deploy attempt just 404s
(`ImageNotFound`), and a naive retry-the-same-request client (like
`examples/demo/seed.py`) piles up orphaned, never-deployed Automater
records instead of erroring cleanly — this bit the very first production
deployment.

```bash
git clone -b main https://github.com/ridvanzengin/custom-telegraf.git /opt/custom-telegraf
cd /opt/custom-telegraf
docker build -t custom-telegraf:latest .
```

First build compiles Telegraf from scratch (a few minutes, real Go
module downloads); subsequent builds after a `git pull` reuse BuildKit's
cache mounts and take ~30s.

---

## 4 — Create the secret env file

```bash
cp /opt/iotops/deploy/iotops/.env.prod.example /opt/iotops/deploy/iotops/.env.prod
nano /opt/iotops/deploy/iotops/.env.prod
# Generate IOTOPS_DB_PASSWORD with: python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

---

## 5 — Add the IoTOps nginx vhost (HTTP-only for now)

```bash
cp /opt/iotops/deploy/nginx/iotops.conf \
   /opt/agritwin/deploy/infra/nginx/conf.d/iotops.conf

docker exec infra-nginx-1 nginx -t
docker exec infra-nginx-1 nginx -s reload
```

The HTTPS server block in `iotops.conf` is fully commented out at this
point — a `listen 443 ssl` block with no matching cert fails `nginx -t`
outright. It gets uncommented in step 10, after a real cert exists.

---

## 6 — Create the database on the shared TimescaleDB container

```bash
docker exec -it infra-db-1 psql -U postgres <<'SQL'
  CREATE DATABASE iotops;
  CREATE USER iotops WITH PASSWORD 'CHANGE_ME';  -- match .env.prod IOTOPS_DB_PASSWORD
  GRANT ALL PRIVILEGES ON DATABASE iotops TO iotops;
  \c iotops
  CREATE EXTENSION IF NOT EXISTS timescaledb;
SQL
```

No `postgis` — confirmed unused in this codebase. Redis needs no
equivalent step: `infra-redis-1`'s `redis` alias already matches every
IoTOps Redis default; only the DB index differs (AgriTwin owns index 0
for its own broker, IoTOps uses index 0 for rule-firing keys and index 1
for its own Celery broker — see the `docker-compose.prod.yml` overrides
and the warning at the bottom of this file).

---

## 7 — Build and start the app

```bash
cd /opt/iotops

docker compose -p iotops --env-file deploy/iotops/.env.prod \
  -f deploy/iotops/docker-compose.prod.yml build

docker compose -p iotops --env-file deploy/iotops/.env.prod \
  -f deploy/iotops/docker-compose.prod.yml up -d
```

`docker-compose.prod.yml` includes a `kafka` service (single-node KRaft
mode, no host port published) — all three demo scenarios (Apiary/MQTT,
Solar/HTTP, Manufacturing/Kafka) work from first boot. It was originally
deferred on the very first deployment (see the deployment plan's
rationale for why) and added back once the rest of the stack had run
stably for a while; if standing this up fresh and want the same
staged rollout, comment out the `kafka` service and demo-showcase's
`KAFKA_BROKER`/`depends_on: kafka` entries, and add them back later.

---

## 8 — Verify over plain HTTP (no DNS needed yet)

```bash
curl --resolve iotops.online:80:<VM_IP> http://iotops.online/
curl --resolve iotops.online:80:<VM_IP> http://iotops.online/api/collector
```

The first should return the frontend's `index.html`; the second real
JSON — confirming the backend actually reached `infra-db-1`/`infra-redis-1`
(the whole reason for the `timescaledb.py` connection-string fix). After
the demo-showcase seed runs and sidecars spin up (about a minute), check:

```bash
docker exec infra-db-1 psql -U iotops -d iotops -c '\dt'
```

Real hypertables with growing row counts confirm telemetry writes are
actually landing, not just that the container started.

---

## 9 — Wait for DNS

```bash
dig +short A iotops.online
```

Don't proceed to step 10 until this returns the VM's IP.

---

## 10 — TLS

```bash
certbot certonly --webroot \
  -w /opt/agritwin/deploy/infra/certbot/webroot \
  -d iotops.online -d www.iotops.online \
  --non-interactive --agree-tos -m your@email.com
```

The VM's existing renewal cron already renews *all* certs regardless of
which one's config it was originally set up for — no new cron line
needed. Then:

1. Uncomment the HTTPS `server` block in
   `/opt/iotops/deploy/nginx/iotops.conf` (the repo copy, so it's
   reviewed and versioned).
2. Re-copy it onto the VM (same command as step 5) and reload:
   ```bash
   cp /opt/iotops/deploy/nginx/iotops.conf \
      /opt/agritwin/deploy/infra/nginx/conf.d/iotops.conf
   docker exec infra-nginx-1 nginx -t
   docker exec infra-nginx-1 nginx -s reload
   ```
3. Verify:
   ```bash
   curl -I https://iotops.online/
   curl -N https://iotops.online/api/event/stream   # should stay open and stream, not hang/buffer
   ```
4. Confirm AgriTwin is unaffected: `curl -I https://agritwin.online/`.

---

## 11 — Systemd auto-start

```bash
cp /opt/iotops/deploy/systemd/iotops-app.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now iotops-app.service
```

`iotops-app.service` depends on `agritwin-infra.service` by name (a
systemd dependency declaration, not a file this repo owns) — the shared
infra must already be enabled on this box.

---

## Deploying Updates

```bash
bash /opt/iotops/deploy/scripts/deploy.sh
```

Pulls the repo, rebuilds images, restarts app services, and only touches
the shared nginx (`nginx -t` then reload) if `deploy/nginx/iotops.conf`
actually changed since the last deploy — routine deploys never reload
AgriTwin's live serving path on an unrelated push.

Doesn't touch `custom-telegraf` — if that repo changes (a plugin fix, a
new upstream Telegraf version), pull and rebuild it separately:

```bash
cd /opt/custom-telegraf && git pull origin main && docker build -t custom-telegraf:latest .
```

---

## Known, accepted risk

`backend`'s `/var/run/docker.sock` bind mount gives that container
root-equivalent control of the **entire host Docker daemon** — including
`agritwin-web-1` and `infra-db-1` — regardless of network isolation.
`DEMO=true` blocks all mutating endpoints, narrowing practical exposure to
whatever's reachable via GET/AI routes, but it isn't zero. This is
inherent to the product, not something this deployment introduces or
fixes. A future cheap mitigation: a `docker-socket-proxy` (Tecnativa's
image) scoped to only the verbs `CollectorDockerManager`/
`AutomaterDockerManager` actually call.

## Shared Redis warning

`infra-redis-1` DB 0 is shared between AgriTwin's Celery broker/result
backend and IoTOps's real-time-rule dedup/firing keys (both default to DB
0). Collision risk is low (distinct key-naming schemes) but **never run
`redis-cli -n 0 FLUSHDB` on this instance.**
