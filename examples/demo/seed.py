"""Idempotently provisions the 3 demo showcase projects (Apiary Monitoring
Demo / MQTT, Solar Farm Demo / HTTP, Manufacturing Line Demo / Kafka)
against the backend's own REST API. Mirrors examples/beekeeping-simulator/
seed.py and examples/data-sources-showcase/seed.py's idempotent-by-name
pattern: every entity is looked up by name and reused if already present,
safe to call on every container start/restart. Not part of the
application itself -- see examples/demo/README.md.
"""

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger("demo_seed")

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://backend:8000")
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
# Lets this idempotent-by-name provisioning step run against a demo
# instance that already has DEMO=true set from first boot -- see
# block_in_demo_mode() in backend/app/dependencies.py. Empty in local dev
# (no-op there; DEMO defaults false anyway), set by docker-compose.prod.yml
# in production.
DEMO_SEED_TOKEN = os.environ.get("DEMO_SEED_TOKEN", "")

RETRY_DELAY_SECONDS = 3
MAX_ATTEMPTS = 40  # ~2 minutes of retrying while Mongo/Timescale/backend warm up


def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{BACKEND_BASE_URL}{path}"
    headers = {"X-Demo-Seed-Token": DEMO_SEED_TOKEN} if DEMO_SEED_TOKEN else {}
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.request(method, url, timeout=10, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        except requests.RequestException as exc:
            last_error = exc
            logger.info("%s %s failed (attempt %s/%s): %s", method, path, attempt, MAX_ATTEMPTS, exc)
            time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"{method} {path} did not succeed after {MAX_ATTEMPTS} attempts") from last_error


def _find_by_name(items: list[dict], name: str) -> dict | None:
    return next((item for item in items if item["name"] == name), None)


def _find_rule(automater: dict, rule_name: str) -> dict | None:
    return next((r for r in automater.get("rules", []) if r["name"] == rule_name), None)


def ensure_project(name: str, description: str) -> str:
    existing = _find_by_name(_request("GET", "/api/project"), name)
    if existing:
        logger.info("Reusing existing project %s (%s)", name, existing["id"])
        return existing["id"]
    created = _request("POST", "/api/project", json={"name": name, "description": description})
    logger.info("Created project %s (%s)", name, created["id"])
    return created["id"]


def ensure_collector(name: str, project_id: str, description: str, inputs: list[dict]) -> str:
    existing = _find_by_name(_request("GET", "/api/collector"), name)
    if existing:
        collector_id = existing["id"]
        logger.info("Reusing existing collector %s (%s)", name, collector_id)
    else:
        created = _request(
            "POST",
            "/api/collector",
            json={
                "project_id": project_id,
                "name": name,
                "description": description,
                "inputs": inputs,
                "outputs": [{"plugin_type": "timescaledb", "configuration": {}}],
            },
        )
        collector_id = created["id"]
        logger.info("Created collector %s (%s)", name, collector_id)

    # Safe to call unconditionally: deploy() force-removes any existing
    # container with the same (deterministic) name before recreating it.
    _request("POST", f"/api/collector/{collector_id}/deployment")
    logger.info("Deployed collector %s", name)
    return collector_id


def ensure_rule(
    project_id: str,
    automater_name: str,
    automater_description: str,
    rule: dict,
    collector_id: str,
) -> str:
    """Returns the real-time Rule's id (existing or newly created) -- the
    caller needs it for a Dashboard panel's event_rule_ids overlay."""
    existing_automater = _find_by_name(_request("GET", "/api/automater"), automater_name)
    if existing_automater:
        existing_rule = _find_rule(existing_automater, rule["name"])
        if existing_rule:
            logger.info("Reusing existing rule %s on automater %s", rule["name"], automater_name)
            return existing_rule["id"]

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
    updated_automater = _request("POST", "/api/automater/rules", json=payload)
    logger.info("Created rule %s on automater %s", rule["name"], automater_name)
    return _find_rule(updated_automater, rule["name"])["id"]


def ensure_query_rule(project_id: str, name: str, fields: dict) -> str:
    """First example fixture to use QueryRuleInput (the scheduled,
    cross-table/time-windowed alternative to the real-time Rule path
    above) -- mirrors ensure_rule's idempotent-by-name shape."""
    existing = _find_by_name(_request("GET", "/api/query-rule"), name)
    if existing:
        logger.info("Reusing existing query rule %s (%s)", name, existing["id"])
        return existing["id"]
    created = _request("POST", "/api/query-rule", json={"project_id": project_id, "name": name, **fields})
    logger.info("Created query rule %s (%s)", name, created["id"])
    return created["id"]


def ensure_dashboard(name: str, project_id: str, description: str, variables: list[dict], panels: list[dict]) -> str:
    existing = _find_by_name(_request("GET", "/api/dashboard"), name)
    if existing:
        logger.info("Reusing existing dashboard %s (%s)", name, existing["id"])
        return existing["id"]
    created = _request(
        "POST",
        "/api/dashboard",
        json={
            "project_id": project_id,
            "name": name,
            "description": description,
            "variables": variables,
            "panels": panels,
        },
    )
    logger.info("Created dashboard %s (%s)", name, created["id"])
    return created["id"]


def _time_filtered_query(table: str, select_clause: str, where: str = "") -> str:
    conditions = [where] if where else []
    conditions.append("time >= $__timeFrom AND time <= $__timeTo")
    return f"SELECT {select_clause} FROM {table} WHERE {' AND '.join(conditions)} ORDER BY time ASC"


# ---------------------------------------------------------------------------
# 1. Apiary Monitoring Demo -- MQTT, two topics/tables on one Collector
# ---------------------------------------------------------------------------

APIARY_PROJECT_NAME = "Apiary Monitoring Demo"
APIARY_COLLECTOR_NAME = "Apiary MQTT Collector"
APIARY_AUTOMATER_NAME = "Apiary Automater"
APIARY_DASHBOARD_NAME = "Apiary Monitoring"
ENV_TABLE = "hive_environment"
WEIGHT_TABLE = "hive_weight"


def _line_panel(table: str, title: str, y_axis: str, x: int, y: int, series_by: str, width: int = 6) -> dict:
    chart = {"type": "line", "title": title, "x_axis": "time", "y_axis": y_axis, "series_by": series_by}
    return {
        "title": title,
        "chart": chart,
        "query": {"sql": _time_filtered_query(table, f"time, {series_by}, {y_axis}")},
        "time_range": "1h",
        "position": {"x": x, "y": y, "width": width, "height": 8},
    }


def ensure_apiary_demo() -> None:
    project_id = ensure_project(
        APIARY_PROJECT_NAME,
        "Apiary environment and weight telemetry across 6 hives -- two MQTT topics, one per table.",
    )
    collector_id = ensure_collector(
        APIARY_COLLECTOR_NAME,
        project_id,
        "Ingests simulated hive environment and weight telemetry from two MQTT topics.",
        [
            {
                "plugin_type": "mqtt",
                "name": "hive-environment-input",
                "configuration": {
                    "topics": ["demo/hive/environment"],
                    "name_override": ENV_TABLE,
                    "tag_keys": ["hive_id"],
                },
            },
            {
                "plugin_type": "mqtt",
                "name": "hive-weight-input",
                "configuration": {
                    "topics": ["demo/hive/weight"],
                    "name_override": WEIGHT_TABLE,
                    "tag_keys": ["hive_id"],
                },
            },
        ],
    )

    temperature_rule_id = ensure_rule(
        project_id,
        APIARY_AUTOMATER_NAME,
        "Evaluates real-time rules against apiary environment telemetry.",
        {
            "name": "high-hive-temperature",
            "category": "apiary",
            "event_type": "temperature_critical",
            "severity": "high",
            "message": "Hive {hive_id} temperature critical: {temperature}°C",
            "table": ENV_TABLE,
            "conditions": [{"column": "temperature", "operator": ">", "value": 38.0}],
            "identifiers": ["hive_id"],
            "ttl": "5m",
        },
        collector_id,
    )

    ensure_query_rule(
        project_id,
        "swarm-risk",
        {
            "description": "Cross-table: elevated 1h average temperature combined with a 1h weight drop.",
            "sql": (
                "SELECT e.hive_id FROM ("
                " SELECT hive_id, AVG(temperature) AS avg_temp_1h"
                " FROM hive_environment WHERE time > now() - interval '1 hour' GROUP BY hive_id"
                ") e JOIN ("
                " SELECT hive_id,"
                " (array_agg(weight_kg ORDER BY time DESC))[1] AS latest_weight,"
                " (array_agg(weight_kg ORDER BY time ASC))[1] AS earliest_weight"
                " FROM hive_weight WHERE time > now() - interval '1 hour' GROUP BY hive_id"
                ") w ON e.hive_id = w.hive_id"
                " WHERE e.avg_temp_1h > 36 AND (w.earliest_weight - w.latest_weight) > 0.5"
            ),
            "identifiers": ["hive_id"],
            "category": "apiary",
            "severity": "high",
            "event_type": "swarm_risk",
            "message": "Hive {hive_id} showing swarm risk: elevated temperature and a recent weight drop.",
            "schedule": {"interval": "5m"},
        },
    )

    ensure_dashboard(
        APIARY_DASHBOARD_NAME,
        project_id,
        "Environment and weight telemetry across 6 hives, two MQTT-sourced tables.",
        [{"name": "hive", "label": "Hive", "table": ENV_TABLE, "value_column": "hive_id"}],
        [
            _line_panel(ENV_TABLE, "Hive Temperature", "temperature", 0, 0, "hive_id"),
            _line_panel(ENV_TABLE, "Hive Humidity", "humidity", 6, 0, "hive_id"),
            _line_panel(ENV_TABLE, "Hive CO2", "co2_ppm", 0, 8, "hive_id"),
            {
                "title": "Latest Hive Sound Level",
                "chart": {"type": "bar", "title": "Latest Hive Sound Level", "x_axis": "hive_id", "y_axis": "sound_level_db"},
                "query": {
                    "sql": (
                        "SELECT DISTINCT ON (hive_id) hive_id, sound_level_db FROM hive_environment "
                        "ORDER BY hive_id, time DESC"
                    )
                },
                "time_range": "1h",
                "position": {"x": 6, "y": 8, "width": 6, "height": 8},
            },
            {
                "title": "Current Hive Weight",
                "chart": {"type": "gauge", "title": "Current Hive Weight", "value_field": "weight_kg", "min": 0, "max": 50},
                "query": {"sql": "SELECT weight_kg FROM hive_weight WHERE hive_id = $hive ORDER BY time DESC LIMIT 1"},
                "time_range": "1h",
                "position": {"x": 0, "y": 16, "width": 4, "height": 8},
            },
            {
                "title": "Temperature vs Humidity",
                "chart": {
                    "type": "line",
                    "title": "Temperature vs Humidity",
                    "x_axis": "time",
                    "y_axis": "temperature",
                    "series": [{"field": "humidity", "axis": "right"}],
                },
                "query": {
                    "sql": _time_filtered_query(ENV_TABLE, "time, temperature, humidity", "hive_id = $hive")
                },
                "time_range": "1h",
                "position": {"x": 4, "y": 16, "width": 8, "height": 8},
            },
            {
                "title": "Hive Temperature (with Alerts)",
                "chart": {"type": "line", "title": "Hive Temperature (with Alerts)", "x_axis": "time", "y_axis": "temperature"},
                "query": {"sql": _time_filtered_query(ENV_TABLE, "time, temperature", "hive_id = $hive")},
                "time_range": "1h",
                "position": {"x": 0, "y": 24, "width": 12, "height": 8},
                "event_rule_ids": [temperature_rule_id],
            },
        ],
    )
    logger.info("Apiary Monitoring Demo provisioned.")


# ---------------------------------------------------------------------------
# 2. Solar Farm Demo -- HTTP push (no broker, needs multi-target push)
# ---------------------------------------------------------------------------

SOLAR_PROJECT_NAME = "Solar Farm Demo"
SOLAR_COLLECTOR_NAME = "Solar HTTP Collector"
SOLAR_AUTOMATER_NAME = "Solar Automater"
SOLAR_DASHBOARD_NAME = "Solar Farm Monitoring"
SOLAR_TABLE = "solar_metrics"
SOLAR_HTTP_PORT = 8092
SOLAR_HTTP_PATH = "/telegraf"


def ensure_solar_demo() -> tuple[str, str]:
    """Returns (project_id, collector_id) -- the collector id is needed
    after rules are created to resolve the final http target url list."""
    project_id = ensure_project(
        SOLAR_PROJECT_NAME, "Solar array output, irradiance, and inverter telemetry pushed over HTTP."
    )
    collector_id = ensure_collector(
        SOLAR_COLLECTOR_NAME,
        project_id,
        "Ingests simulated solar array telemetry via HTTP webhook push.",
        [
            {
                "plugin_type": "http",
                "name": "solar-http-input",
                "configuration": {
                    "service_address": f"tcp://:{SOLAR_HTTP_PORT}",
                    "paths": [SOLAR_HTTP_PATH],
                    "name_override": SOLAR_TABLE,
                    "tag_keys": ["panel_array_id"],
                },
            }
        ],
    )

    overheating_rule_id = ensure_rule(
        project_id,
        SOLAR_AUTOMATER_NAME,
        "Evaluates real-time rules against solar array telemetry.",
        {
            "name": "panel-overheating",
            "category": "solar",
            "event_type": "panel_overheating",
            "severity": "high",
            "message": "Array {panel_array_id} panel overheating: {panel_temp_c}°C",
            "table": SOLAR_TABLE,
            "conditions": [{"column": "panel_temp_c", "operator": ">", "value": 65.0}],
            "identifiers": ["panel_array_id"],
            "ttl": "5m",
        },
        collector_id,
    )

    ensure_query_rule(
        project_id,
        "underperformance",
        {
            "description": "6h average output below expected baseline -- gradual degradation, not a spike.",
            "sql": (
                "SELECT panel_array_id FROM solar_metrics WHERE time > now() - interval '6 hours' "
                "GROUP BY panel_array_id HAVING AVG(power_output_kw) < 2.0"
            ),
            "identifiers": ["panel_array_id"],
            "category": "solar",
            "severity": "medium",
            "event_type": "underperformance",
            "message": "Array {panel_array_id} underperforming over the last 6 hours.",
            "schedule": {"interval": "10m"},
        },
    )

    ensure_dashboard(
        SOLAR_DASHBOARD_NAME,
        project_id,
        "Output, irradiance, and inverter telemetry across 3 solar arrays, HTTP-sourced.",
        [{"name": "array", "label": "Array", "table": SOLAR_TABLE, "value_column": "panel_array_id"}],
        [
            _line_panel(SOLAR_TABLE, "Power Output", "power_output_kw", 0, 0, "panel_array_id"),
            _line_panel(SOLAR_TABLE, "Irradiance", "irradiance_w_m2", 6, 0, "panel_array_id"),
            {
                "title": "Latest Power Output by Array",
                "chart": {"type": "bar", "title": "Latest Power Output by Array", "x_axis": "panel_array_id", "y_axis": "power_output_kw"},
                "query": {
                    "sql": (
                        "SELECT DISTINCT ON (panel_array_id) panel_array_id, power_output_kw FROM solar_metrics "
                        "ORDER BY panel_array_id, time DESC"
                    )
                },
                "time_range": "1h",
                "position": {"x": 0, "y": 8, "width": 6, "height": 8},
            },
            {
                "title": "Current Inverter Efficiency",
                "chart": {
                    "type": "gauge",
                    "title": "Current Inverter Efficiency",
                    "value_field": "inverter_efficiency_pct",
                    "min": 0,
                    "max": 100,
                },
                "query": {
                    "sql": "SELECT inverter_efficiency_pct FROM solar_metrics WHERE panel_array_id = $array ORDER BY time DESC LIMIT 1"
                },
                "time_range": "1h",
                "position": {"x": 6, "y": 8, "width": 6, "height": 8},
            },
            {
                "title": "Power Output vs Irradiance",
                "chart": {
                    "type": "line",
                    "title": "Power Output vs Irradiance",
                    "x_axis": "time",
                    "y_axis": "power_output_kw",
                    "series": [{"field": "irradiance_w_m2", "axis": "right"}],
                },
                "query": {
                    "sql": _time_filtered_query(SOLAR_TABLE, "time, power_output_kw, irradiance_w_m2", "panel_array_id = $array")
                },
                "time_range": "1h",
                "position": {"x": 0, "y": 16, "width": 12, "height": 8},
            },
            {
                "title": "Panel Temperature (with Alerts)",
                "chart": {"type": "line", "title": "Panel Temperature (with Alerts)", "x_axis": "time", "y_axis": "panel_temp_c"},
                "query": {"sql": _time_filtered_query(SOLAR_TABLE, "time, panel_temp_c", "panel_array_id = $array")},
                "time_range": "1h",
                "position": {"x": 0, "y": 24, "width": 12, "height": 8},
                "event_rule_ids": [overheating_rule_id],
            },
        ],
    )
    logger.info("Solar Farm Demo provisioned.")
    return project_id, collector_id


def _solar_http_target_urls(collector_id: str) -> list[str]:
    """http_listener_v2 has no broker -- see solar_publisher.py's own
    docstring. Returns the Collector's own target plus every Automater
    currently covering SOLAR_TABLE (today just SOLAR_AUTOMATER_NAME, but
    looked up rather than assumed)."""
    urls = [f"http://iotops-collector-{collector_id}:{SOLAR_HTTP_PORT}{SOLAR_HTTP_PATH}"]
    for automater in _request("GET", "/api/automater"):
        if any(i["configuration"].get("name_override") == SOLAR_TABLE for i in automater["inputs"]):
            urls.append(f"http://iotops-automater-{automater['id']}:{SOLAR_HTTP_PORT}{SOLAR_HTTP_PATH}")
    return urls


# ---------------------------------------------------------------------------
# 3. Manufacturing Line Demo -- Kafka
# ---------------------------------------------------------------------------

MANUFACTURING_PROJECT_NAME = "Manufacturing Line Demo"
MANUFACTURING_COLLECTOR_NAME = "Manufacturing Kafka Collector"
MANUFACTURING_AUTOMATER_NAME = "Manufacturing Automater"
MANUFACTURING_DASHBOARD_NAME = "Manufacturing Line Monitoring"
MACHINE_TABLE = "machine_telemetry"


def ensure_manufacturing_demo() -> None:
    project_id = ensure_project(
        MANUFACTURING_PROJECT_NAME,
        "Machine vibration, RPM, and motor telemetry across 3 machines, Kafka-sourced.",
    )
    collector_id = ensure_collector(
        MANUFACTURING_COLLECTOR_NAME,
        project_id,
        "Ingests simulated manufacturing line telemetry from Kafka.",
        [
            {
                "plugin_type": "kafka",
                "name": "manufacturing-kafka-input",
                "configuration": {
                    "brokers": [KAFKA_BROKER],
                    "topics": ["manufacturing.line.telemetry"],
                    "name_override": MACHINE_TABLE,
                    "tag_keys": ["machine_id"],
                },
            }
        ],
    )

    vibration_rule_id = ensure_rule(
        project_id,
        MANUFACTURING_AUTOMATER_NAME,
        "Evaluates real-time rules against manufacturing line telemetry.",
        {
            "name": "high-vibration",
            "category": "manufacturing",
            "event_type": "vibration_critical",
            "severity": "high",
            "message": "Machine {machine_id} vibration critical: {vibration_rms} mm/s RMS",
            "table": MACHINE_TABLE,
            "conditions": [{"column": "vibration_rms", "operator": ">", "value": 7.5}],
            "identifiers": ["machine_id"],
            "ttl": "5m",
        },
        collector_id,
    )

    ensure_query_rule(
        project_id,
        "rpm-drift",
        {
            "description": "RPM outside its expected band together with elevated motor temperature.",
            "sql": (
                "SELECT machine_id FROM machine_telemetry WHERE time > now() - interval '1 hour' "
                "GROUP BY machine_id HAVING (AVG(rpm) < 1800 OR AVG(rpm) > 2200) AND AVG(motor_temp_c) > 80"
            ),
            "identifiers": ["machine_id"],
            "category": "manufacturing",
            "severity": "medium",
            "event_type": "rpm_drift",
            "message": "Machine {machine_id} showing RPM/temperature drift over the last hour.",
            "schedule": {"interval": "10m"},
        },
    )

    ensure_dashboard(
        MANUFACTURING_DASHBOARD_NAME,
        project_id,
        "Vibration, RPM, and motor telemetry across 3 machines, Kafka-sourced.",
        [{"name": "machine", "label": "Machine", "table": MACHINE_TABLE, "value_column": "machine_id"}],
        [
            _line_panel(MACHINE_TABLE, "Machine Vibration", "vibration_rms", 0, 0, "machine_id"),
            _line_panel(MACHINE_TABLE, "Motor Temperature", "motor_temp_c", 6, 0, "machine_id"),
            {
                "title": "Latest Current Draw by Machine",
                "chart": {"type": "bar", "title": "Latest Current Draw by Machine", "x_axis": "machine_id", "y_axis": "current_draw_amps"},
                "query": {
                    "sql": (
                        "SELECT DISTINCT ON (machine_id) machine_id, current_draw_amps FROM machine_telemetry "
                        "ORDER BY machine_id, time DESC"
                    )
                },
                "time_range": "1h",
                "position": {"x": 0, "y": 8, "width": 6, "height": 8},
            },
            {
                "title": "Current RPM",
                "chart": {"type": "gauge", "title": "Current RPM", "value_field": "rpm", "min": 0, "max": 3000},
                "query": {"sql": "SELECT rpm FROM machine_telemetry WHERE machine_id = $machine ORDER BY time DESC LIMIT 1"},
                "time_range": "1h",
                "position": {"x": 6, "y": 8, "width": 6, "height": 8},
            },
            {
                "title": "RPM vs Motor Temperature",
                "chart": {
                    "type": "line",
                    "title": "RPM vs Motor Temperature",
                    "x_axis": "time",
                    "y_axis": "rpm",
                    "series": [{"field": "motor_temp_c", "axis": "right"}],
                },
                "query": {
                    "sql": _time_filtered_query(MACHINE_TABLE, "time, rpm, motor_temp_c", "machine_id = $machine")
                },
                "time_range": "1h",
                "position": {"x": 0, "y": 16, "width": 12, "height": 8},
            },
            {
                "title": "Vibration (with Alerts)",
                "chart": {"type": "line", "title": "Vibration (with Alerts)", "x_axis": "time", "y_axis": "vibration_rms"},
                "query": {"sql": _time_filtered_query(MACHINE_TABLE, "time, vibration_rms", "machine_id = $machine")},
                "time_range": "1h",
                "position": {"x": 0, "y": 24, "width": 12, "height": 8},
                "event_rule_ids": [vibration_rule_id],
            },
        ],
    )
    logger.info("Manufacturing Line Demo provisioned.")


def ensure_demo_provisioned() -> list[str]:
    """Returns the Solar Farm Demo's HTTP target URLs -- only known once
    the Collector's and any covering Automater's ids are resolved."""
    ensure_apiary_demo()
    _, solar_collector_id = ensure_solar_demo()
    ensure_manufacturing_demo()
    logger.info("All 3 demo showcase projects provisioned.")
    return _solar_http_target_urls(solar_collector_id)
