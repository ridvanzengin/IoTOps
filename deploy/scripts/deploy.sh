#!/usr/bin/env bash
# deploy.sh -- pull latest code, rebuild images, restart app services.
# Does NOT touch the shared infra project (db/redis/nginx stay up).
# Run from: /opt/iotops
set -euo pipefail

cd /opt/iotops

COMPOSE="docker compose -p iotops --env-file deploy/iotops/.env.prod -f deploy/iotops/docker-compose.prod.yml"

echo "[deploy] Pulling latest code..."
git pull origin main

echo "[deploy] Building images..."
$COMPOSE build

echo "[deploy] Restarting app services..."
$COMPOSE up -d --no-deps mongo mosquitto backend celery-worker celery-beat frontend demo-showcase

# The shared nginx serves agritwin.online live -- only touch it, and only
# reload, when this repo's own vhost source actually changed. A bad config
# must never make it past `nginx -t` into a reload.
NGINX_SRC="deploy/nginx/iotops.conf"
NGINX_DST="/opt/agritwin/deploy/infra/nginx/conf.d/iotops.conf"
if ! cmp -s "$NGINX_SRC" "$NGINX_DST" 2>/dev/null; then
  echo "[deploy] nginx vhost changed, updating..."
  cp "$NGINX_DST" "${NGINX_DST}.bak" 2>/dev/null || true
  cp "$NGINX_SRC" "$NGINX_DST"
  if docker exec infra-nginx-1 nginx -t; then
    docker exec infra-nginx-1 nginx -s reload
    echo "[deploy] nginx reloaded."
  else
    echo "[deploy] nginx -t FAILED -- reverting, not reloading." >&2
    [ -f "${NGINX_DST}.bak" ] && mv "${NGINX_DST}.bak" "$NGINX_DST"
    exit 1
  fi
else
  echo "[deploy] nginx vhost unchanged, skipping."
fi

echo "[deploy] Done."
$COMPOSE ps
