"""Idempotently provisions the Data Sources Showcase demo (Project, two
Collectors, three Rules, one Dashboard) against the backend's own REST
API. Demonstrates the non-MQTT input plugins (kafka, http, amqp) end to
end -- see iotops-workspace/ROADMAP.md's data-sources note. Not part of
the application itself -- see examples/data-sources-showcase/README.md.

Mirrors examples/beekeeping-simulator/seed.py's idempotent-by-name
pattern: every entity is looked up by name and reused if already
present, safe to call on every container start/restart.
"""

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger("data_sources_seed")

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://backend:8000")
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")

PROJECT_NAME = "Data Sources Showcase"
KAFKA_COLLECTOR_NAME = "Factory Floor Kafka Collector"
WEBQUEUE_COLLECTOR_NAME = "Web & Queue Collector"
KAFKA_AUTOMATER_NAME = "Factory Floor Automater"
WEBQUEUE_AUTOMATER_NAME = "Web & Queue Automater"
DASHBOARD_NAME = "Data Sources Overview"

KAFKA_TABLE = "kafka_metrics"
HTTP_TABLE = "http_metrics"
AMQP_TABLE = "amqp_metrics"

KAFKA_TOPIC = "factory.machines"
HTTP_PORT = 8090
HTTP_PATH = "/telegraf"
AMQP_EXCHANGE = "fleet.telemetry"
AMQP_QUEUE = "fleet-telemetry-collector"

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
            "description": "Demonstrates the kafka/http/amqp Collector input plugins end to end.",
        },
    )
    logger.info("Created project %s", created["id"])
    return created["id"]


def ensure_kafka_collector(project_id: str) -> str:
    existing = _find_by_name(_request("GET", "/api/collector"), KAFKA_COLLECTOR_NAME)
    if existing:
        collector_id = existing["id"]
        logger.info("Reusing existing collector %s", collector_id)
    else:
        created = _request(
            "POST",
            "/api/collector",
            json={
                "project_id": project_id,
                "name": KAFKA_COLLECTOR_NAME,
                "description": "Ingests simulated factory-floor sensor telemetry from Kafka.",
                "inputs": [
                    {
                        "plugin_type": "kafka",
                        "name": "factory-kafka-input",
                        "configuration": {
                            "brokers": [KAFKA_BROKER],
                            "topics": [KAFKA_TOPIC],
                            "name_override": KAFKA_TABLE,
                            "tag_keys": ["machine_id", "zone"],
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


def ensure_webqueue_collector(project_id: str) -> str:
    existing = _find_by_name(_request("GET", "/api/collector"), WEBQUEUE_COLLECTOR_NAME)
    if existing:
        collector_id = existing["id"]
        logger.info("Reusing existing collector %s", collector_id)
    else:
        created = _request(
            "POST",
            "/api/collector",
            json={
                "project_id": project_id,
                "name": WEBQUEUE_COLLECTOR_NAME,
                "description": "Ingests simulated weather-station telemetry via HTTP webhook and "
                "delivery-fleet telemetry via AMQP -- two input plugins, one Collector.",
                "inputs": [
                    {
                        "plugin_type": "http",
                        "name": "weather-http-input",
                        "configuration": {
                            "service_address": f"tcp://:{HTTP_PORT}",
                            "paths": [HTTP_PATH],
                            "name_override": HTTP_TABLE,
                            "tag_keys": ["station_id", "city"],
                        },
                    },
                    {
                        "plugin_type": "amqp",
                        "name": "fleet-amqp-input",
                        "configuration": {
                            "brokers": [f"amqp://{RABBITMQ_HOST}:5672/"],
                            "exchange": AMQP_EXCHANGE,
                            "queue": AMQP_QUEUE,
                            "binding_key": "#",
                            "name_override": AMQP_TABLE,
                            "tag_keys": ["vehicle_id", "route"],
                        },
                    },
                ],
                "outputs": [{"plugin_type": "timescaledb", "configuration": {}}],
            },
        )
        collector_id = created["id"]
        logger.info("Created collector %s", collector_id)

    _request("POST", f"/api/collector/{collector_id}/deployment")
    logger.info("Deployed collector %s", collector_id)
    return collector_id


def _find_rule(automater: dict, rule_name: str) -> dict | None:
    return next((r for r in automater.get("rules", []) if r["name"] == rule_name), None)


def ensure_rule(
    project_id: str,
    automater_name: str,
    automater_description: str,
    rule: dict,
    collector_id: str,
) -> None:
    existing_automater = _find_by_name(_request("GET", "/api/automater"), automater_name)
    if existing_automater and _find_rule(existing_automater, rule["name"]):
        logger.info("Reusing existing rule %s on automater %s", rule["name"], automater_name)
        return

    payload = {
        "project_id": project_id,
        "rule": rule,
        "automater_id": existing_automater["id"] if existing_automater else None,
        "automater_name": None if existing_automater else automater_name,
        "automater_description": "" if existing_automater else automater_description,
        # Needed both for a brand new Automater and for an existing one
        # that doesn't have an input for this rule's table yet -- unused
        # (but harmless to pass) when reusing an already-covered table.
        "collector_id": collector_id,
    }
    _request("POST", "/api/automater/rules", json=payload)
    logger.info("Created rule %s on automater %s", rule["name"], automater_name)


def ensure_rules(project_id: str, kafka_collector_id: str, webqueue_collector_id: str) -> None:
    ensure_rule(
        project_id,
        KAFKA_AUTOMATER_NAME,
        "Evaluates rules against factory-floor Kafka telemetry.",
        {
            "name": "high-vibration",
            "category": "factory",
            "event_type": "vibration_spike",
            "severity": "high",
            "message": "Machine {machine_id} vibration spike: {vibration_mm_s} mm/s",
            "table": KAFKA_TABLE,
            "conditions": [{"column": "vibration_mm_s", "operator": ">", "value": 9.0}],
            "identifiers": ["machine_id"],
            "ttl": "2m",
        },
        kafka_collector_id,
    )
    ensure_rule(
        project_id,
        WEBQUEUE_AUTOMATER_NAME,
        "Evaluates rules against HTTP/AMQP telemetry.",
        {
            "name": "high-wind",
            "category": "weather",
            "event_type": "wind_spike",
            "severity": "medium",
            "message": "Station {station_id} high wind: {wind_speed_kmh} km/h",
            "table": HTTP_TABLE,
            "conditions": [{"column": "wind_speed_kmh", "operator": ">", "value": 40.0}],
            "identifiers": ["station_id"],
            "ttl": "2m",
        },
        webqueue_collector_id,
    )
    # Second rule on the same Automater, different table -- create_rule
    # adds the amqp input to it automatically since it doesn't cover
    # amqp_metrics yet. See ROADMAP.md's "Multi-table Automaters" note.
    ensure_rule(
        project_id,
        WEBQUEUE_AUTOMATER_NAME,
        "Evaluates rules against HTTP/AMQP telemetry.",
        {
            "name": "low-fuel",
            "category": "fleet",
            "event_type": "low_fuel",
            "severity": "medium",
            "message": "Vehicle {vehicle_id} low fuel: {fuel_pct}%",
            "table": AMQP_TABLE,
            "conditions": [{"column": "fuel_pct", "operator": "<", "value": 15.0}],
            "identifiers": ["vehicle_id"],
            "ttl": "2m",
        },
        webqueue_collector_id,
    )


def _time_filtered_query(table: str, select_clause: str) -> str:
    return f"SELECT {select_clause} FROM {table} WHERE time >= $__timeFrom AND time <= $__timeTo ORDER BY time ASC"


def _panel(title: str, table: str, y_axis: str, series_by: str, x: int, y: int) -> dict:
    select_clause = f"time, {series_by}, {y_axis}"
    return {
        "title": title,
        "chart": {"type": "line", "title": title, "x_axis": "time", "y_axis": y_axis, "series_by": series_by},
        "query": {"sql": _time_filtered_query(table, select_clause)},
        "time_range": "1h",
        "position": {"x": x, "y": y, "width": 6, "height": 8},
    }


def ensure_dashboard(project_id: str) -> str:
    existing = _find_by_name(_request("GET", "/api/dashboard"), DASHBOARD_NAME)
    if existing:
        logger.info("Reusing existing dashboard %s", existing["id"])
        return existing["id"]

    payload = {
        "project_id": project_id,
        "name": DASHBOARD_NAME,
        "description": "One panel per non-MQTT data source: Kafka, HTTP, and AMQP.",
        "variables": [],
        "panels": [
            _panel("Factory Vibration (Kafka)", KAFKA_TABLE, "vibration_mm_s", "machine_id", 0, 0),
            _panel("Weather Wind Speed (HTTP)", HTTP_TABLE, "wind_speed_kmh", "station_id", 6, 0),
            _panel("Fleet Fuel Level (AMQP)", AMQP_TABLE, "fuel_pct", "vehicle_id", 0, 8),
        ],
    }
    created = _request("POST", "/api/dashboard", json=payload)
    logger.info("Created dashboard %s", created["id"])
    return created["id"]


def _http_target_urls(webqueue_collector_id: str) -> list[str]:
    """Kafka/AMQP are broker-mediated pub/sub: the Collector's and
    Automater's consumers each independently connect *out* to the same
    broker (Kafka topic / AMQP exchange) and both get their own full copy
    of the stream for free, no publisher awareness needed. HTTP has no
    broker -- http_listener_v2 is a plain point-to-point push target, so
    whoever's publishing has to push to *every* listener that needs the
    data, or only the first one ever sees it. This is a genuine
    architectural gap specific to push-based inputs, not something this
    demo works around invisibly -- see the README's own note and
    iotops-workspace/ROADMAP.md's data-sources entry. Real fix belongs in
    the Automater deploy path (reusing the Collector's own listener
    process for push-based plugin types instead of spinning up a second,
    unreachable one), out of scope for this showcase.

    Returns the Collector's own target plus every Automater currently
    covering HTTP_TABLE (today just the one Web & Queue Automater, but
    looked up rather than assumed so this keeps working if that ever
    changes).
    """
    urls = [f"http://iotops-collector-{webqueue_collector_id}:{HTTP_PORT}{HTTP_PATH}"]
    for automater in _request("GET", "/api/automater"):
        if any(i["configuration"].get("name_override") == HTTP_TABLE for i in automater["inputs"]):
            urls.append(f"http://iotops-automater-{automater['id']}:{HTTP_PORT}{HTTP_PATH}")
    return urls


def ensure_demo_provisioned() -> list[str]:
    """Returns the HTTP target URLs the http_publisher should push to --
    only known once the Collector's and any covering Automater's ids
    (and thus their deterministic container names, see
    app/collector/docker.py's/app/automater/docker.py's _container_name)
    are resolved."""
    project_id = ensure_project()
    kafka_collector_id = ensure_kafka_collector(project_id)
    webqueue_collector_id = ensure_webqueue_collector(project_id)
    ensure_rules(project_id, kafka_collector_id, webqueue_collector_id)
    ensure_dashboard(project_id)
    logger.info("Data Sources Showcase demo provisioned.")
    return _http_target_urls(webqueue_collector_id)
