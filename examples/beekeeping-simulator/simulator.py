"""Simulates bee hive telemetry (temperature/humidity/weight) across multiple
apiaries and hives, and publishes it to MQTT. Part of the Beekeeping Showcase
(Milestone 4) -- the first end-to-end platform demo. Not part of the
application itself; see examples/beekeeping-simulator/README.md.
"""

import json
import logging
import os
import random
import time

import paho.mqtt.client as mqtt

logger = logging.getLogger("beekeeping_simulator")

BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "mosquitto")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "3"))

HIVE_TOPIC = "beekeeping/hive"

HIVES = [
    {"apiary_id": "apiary-1", "hive_id": "hive-1", "base_weight": 32.0},
    {"apiary_id": "apiary-1", "hive_id": "hive-2", "base_weight": 35.5},
    {"apiary_id": "apiary-1", "hive_id": "hive-3", "base_weight": 29.0},
    {"apiary_id": "apiary-2", "hive_id": "hive-4", "base_weight": 38.0},
    {"apiary_id": "apiary-2", "hive_id": "hive-5", "base_weight": 31.5},
    {"apiary_id": "apiary-2", "hive_id": "hive-6", "base_weight": 34.0},
]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class HiveState:
    """Small persistent random walk per hive, reverting gently toward a
    healthy-brood-nest midpoint, so charts look like real sensor readings
    instead of independent noise every tick."""

    def __init__(self, base_weight: float) -> None:
        self.temperature = 34.5
        self.humidity = 60.0
        self.weight = base_weight

    def step(self) -> dict:
        self.temperature = _clamp(
            self.temperature + random.uniform(-0.3, 0.3) + (34.5 - self.temperature) * 0.05,
            30.0,
            38.0,
        )
        self.humidity = _clamp(
            self.humidity + random.uniform(-1.0, 1.0) + (60.0 - self.humidity) * 0.05,
            45.0,
            75.0,
        )
        # Net upward drift simulates nectar flow; occasional small dips
        # simulate bees consuming stores.
        self.weight = max(0.0, self.weight + random.uniform(-0.05, 0.12))
        return {
            "temperature": round(self.temperature, 2),
            "humidity": round(self.humidity, 2),
            "weight": round(self.weight, 2),
        }


def build_payload(hive: dict, state: HiveState) -> dict:
    return {
        "apiary_id": hive["apiary_id"],
        "hive_id": hive["hive_id"],
        **state.step(),
    }


def publish_forever() -> None:
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    logger.info("Connected to %s:%s, publishing every %ss", BROKER_HOST, BROKER_PORT, PUBLISH_INTERVAL_SECONDS)

    states = {hive["hive_id"]: HiveState(hive["base_weight"]) for hive in HIVES}

    try:
        while True:
            for hive in HIVES:
                payload = build_payload(hive, states[hive["hive_id"]])
                client.publish(HIVE_TOPIC, json.dumps(payload))
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    publish_forever()
