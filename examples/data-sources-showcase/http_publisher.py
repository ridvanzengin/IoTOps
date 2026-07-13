"""Publishes synthetic weather-station telemetry to one or more
http_listener_v2 endpoints. Part of the Data Sources Showcase; not part
of the application itself -- see examples/data-sources-showcase/README.md.

Unlike kafka_publisher/amqp_publisher (which connect out to a fixed,
statically-named broker service that fans a single publish out to every
consumer on its own), http_listener_v2 is a plain point-to-point push
target with no broker in between -- so this module takes a *list* of
target URLs (the Collector's own, plus any Automater's that also needs
the same data) and pushes every payload to each of them. See seed.py's
_http_target_urls for why more than one target is needed at all.
"""

import logging
import math
import os
import random
import time

import requests

logger = logging.getLogger("http_publisher")

PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "3"))

STATIONS = [
    {"station_id": "wx-01", "city": "seattle"},
    {"station_id": "wx-02", "city": "chicago"},
    {"station_id": "wx-03", "city": "miami"},
]

_start = time.time()


def _build_payload(station: dict) -> dict:
    t = time.time() - _start
    phase = hash(station["station_id"]) % 100 / 100 * math.tau
    wind_speed = round(35.0 + 10.0 * math.sin(t / 20 + phase) + random.uniform(-1.0, 1.0), 2)
    temperature = round(18.0 + random.uniform(-3.0, 3.0), 2)
    return {**station, "wind_speed_kmh": wind_speed, "temperature_c": temperature}


def publish_forever(target_urls: list[str]) -> None:
    logger.info("Pushing to %s every %ss", target_urls, PUBLISH_INTERVAL_SECONDS)
    while True:
        for station in STATIONS:
            payload = _build_payload(station)
            for target_url in target_urls:
                try:
                    requests.post(target_url, json=payload, timeout=5)
                except requests.RequestException as exc:
                    # Expected for a while at startup -- the Collector/
                    # Automater container takes a few seconds to deploy
                    # after seed.py provisions it.
                    logger.info("push to %s failed (not up yet?): %s", target_url, exc)
        time.sleep(PUBLISH_INTERVAL_SECONDS)
