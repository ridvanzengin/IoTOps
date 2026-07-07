"""Idempotently provisions the Beekeeping Showcase demo (Project, Collector,
Dashboard) against the backend's own REST API. Part of the Beekeeping
Showcase (Milestone 4); not part of the application itself -- see
examples/beekeeping-simulator/README.md.

Each entity is looked up by name and reused if already present, so this is
safe to call on every container start/restart without erroring or
duplicating entities -- necessary since the container restarts on crash
(restart: unless-stopped in docker-compose.yml) and there is no compose
healthcheck to gate startup on the backend/Mongo/Timescale actually being
ready to serve requests.
"""

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger("beekeeping_seed")

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://backend:8000")

PROJECT_NAME = "Beekeeping Showcase"
COLLECTOR_NAME = "Beekeeping Hive Collector"
DASHBOARD_NAME = "Beekeeping Overview"
TABLE_NAME = "hive_metrics"

RETRY_DELAY_SECONDS = 3
MAX_ATTEMPTS = 40  # ~2 minutes of retrying while Mongo/Timescale/backend warm up


def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{BACKEND_BASE_URL}{path}"
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.request(method, url, timeout=10, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        except requests.RequestException as exc:
            last_error = exc
            logger.info("%s %s failed (attempt %s/%s): %s", method, path, attempt, MAX_ATTEMPTS, exc)
            time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"{method} {path} did not succeed after {MAX_ATTEMPTS} attempts") from last_error


def _find_by_name(items: list[dict], name: str) -> dict | None:
    return next((item for item in items if item["name"] == name), None)


def ensure_project() -> str:
    existing = _find_by_name(_request("GET", "/api/project"), PROJECT_NAME)
    if existing:
        logger.info("Reusing existing project %s", existing["id"])
        return existing["id"]

    created = _request(
        "POST",
        "/api/project",
        json={
            "name": PROJECT_NAME,
            "description": "First domain showcase - simulated hive telemetry across two apiaries.",
        },
    )
    logger.info("Created project %s", created["id"])
    return created["id"]


def ensure_collector(project_id: str) -> str:
    existing = _find_by_name(_request("GET", "/api/collector"), COLLECTOR_NAME)
    if existing:
        collector_id = existing["id"]
        logger.info("Reusing existing collector %s", collector_id)
    else:
        created = _request(
            "POST",
            "/api/collector",
            json={
                "project_id": project_id,
                "name": COLLECTOR_NAME,
                "description": "Ingests simulated hive telemetry into TimescaleDB.",
                "inputs": [
                    {
                        "plugin_type": "mqtt",
                        "name": "hive-input",
                        "configuration": {
                            "topics": ["beekeeping/hive"],
                            "name_override": TABLE_NAME,
                            "tag_keys": ["apiary_id", "hive_id"],
                        },
                    }
                ],
                "outputs": [{"plugin_type": "timescaledb", "configuration": {}}],
            },
        )
        collector_id = created["id"]
        logger.info("Created collector %s", collector_id)

    # Safe to call unconditionally: deploy() force-removes any existing
    # container with the same (deterministic) name before recreating it.
    _request("POST", f"/api/collector/{collector_id}/deployment")
    logger.info("Deployed collector %s", collector_id)
    return collector_id


def _time_filtered_query(select_clause: str, where: str = "") -> str:
    conditions = [where] if where else []
    conditions.append("time >= $__timeFrom AND time <= $__timeTo")
    return f"SELECT {select_clause} FROM {TABLE_NAME} WHERE {' AND '.join(conditions)} ORDER BY time ASC"


def _panel(
    title: str,
    y_axis: str,
    x: int,
    y: int,
    where: str = "",
    series_by: str | None = None,
    width: int = 6,
    height: int = 8,
) -> dict:
    select_clause = f"time, hive_id, {y_axis}" if series_by else f"time, {y_axis}"
    chart: dict[str, Any] = {"type": "line", "title": title, "x_axis": "time", "y_axis": y_axis}
    if series_by:
        chart["series_by"] = series_by
    return {
        "title": title,
        "chart": chart,
        "query": {"sql": _time_filtered_query(select_clause, where)},
        "time_range": "1h",
        "position": {"x": x, "y": y, "width": width, "height": height},
    }


def ensure_dashboard(project_id: str) -> str:
    existing = _find_by_name(_request("GET", "/api/dashboard"), DASHBOARD_NAME)
    if existing:
        logger.info("Reusing existing dashboard %s", existing["id"])
        return existing["id"]

    per_hive_where = "apiary_id = $apiary AND hive_id = $hive"
    payload = {
        "project_id": project_id,
        "name": DASHBOARD_NAME,
        "description": "Simulated hive temperature, humidity, and weight across two apiaries.",
        "variables": [
            {"name": "apiary", "label": "Apiary", "table": TABLE_NAME, "value_column": "apiary_id"},
            {
                "name": "hive",
                "label": "Hive",
                "table": TABLE_NAME,
                "value_column": "hive_id",
                "predicate_column": "apiary_id",
                "predicate_variable": "apiary",
            },
        ],
        "panels": [
            _panel("Hive Temperature", "temperature", 0, 0, per_hive_where),
            _panel("Hive Humidity", "humidity", 6, 0, per_hive_where),
            _panel("Hive Weight", "weight", 0, 8, per_hive_where),
            _panel(
                "Apiary Hives Temperature",
                "temperature",
                6,
                8,
                where="apiary_id = $apiary",
                series_by="hive_id",
            ),
            _panel(
                "All Hives Weight",
                "weight",
                0,
                16,
                series_by="hive_id",
                width=12,
            ),
        ],
    }
    created = _request("POST", "/api/dashboard", json=payload)
    logger.info("Created dashboard %s", created["id"])
    return created["id"]


def ensure_demo_provisioned() -> None:
    project_id = ensure_project()
    ensure_collector(project_id)
    ensure_dashboard(project_id)
    logger.info("Beekeeping showcase demo provisioned.")
