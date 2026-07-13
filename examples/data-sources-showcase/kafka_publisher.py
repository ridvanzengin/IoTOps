"""Publishes synthetic factory-floor sensor telemetry to Kafka. Part of
the Data Sources Showcase; not part of the application itself -- see
examples/data-sources-showcase/README.md.
"""

import json
import logging
import math
import os
import random
import time

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

logger = logging.getLogger("kafka_publisher")

KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = "factory.machines"
PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "3"))

MACHINES = [
    {"machine_id": "press-01", "zone": "line-a"},
    {"machine_id": "press-02", "zone": "line-a"},
    {"machine_id": "lathe-01", "zone": "line-b"},
]

# Slow per-machine phase offset so each oscillates independently around
# the threshold a test rule would likely use (vibration_mm_s > 9.0),
# giving repeated match/clear crossings instead of a static always-true
# or always-false value -- same shape as rule-testing-publisher's own
# temperature oscillation.
_start = time.time()


def _build_payload(machine: dict) -> dict:
    t = time.time() - _start
    phase = hash(machine["machine_id"]) % 100 / 100 * math.tau
    vibration = round(8.0 + 3.0 * math.sin(t / 25 + phase) + random.uniform(-0.4, 0.4), 2)
    temperature = round(45.0 + random.uniform(-2.0, 2.0), 2)
    return {**machine, "vibration_mm_s": vibration, "temperature_c": temperature}


def _connect() -> KafkaProducer:
    attempt = 0
    while True:
        try:
            return KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except NoBrokersAvailable:
            attempt += 1
            logger.info("Kafka broker not ready yet (attempt %s)", attempt)
            time.sleep(3)


def publish_forever() -> None:
    producer = _connect()
    logger.info("Connected to Kafka at %s, publishing every %ss", KAFKA_BROKER, PUBLISH_INTERVAL_SECONDS)

    try:
        while True:
            for machine in MACHINES:
                producer.send(KAFKA_TOPIC, _build_payload(machine))
            producer.flush()
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    finally:
        producer.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    publish_forever()
