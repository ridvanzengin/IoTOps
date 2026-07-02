"""Publishes synthetic telemetry to verify the Collector -> MQTT -> TimescaleDB
pipeline end to end. Not part of the application; a manual verification tool
for Milestone 2. See examples/mqtt-publisher/README.md.
"""

import json
import logging
import os
import random
import time

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mqtt_publisher")

BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "mosquitto")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "2"))

METRICS_TOPIC = "telemetry/metrics"
STATUS_TOPIC = "telemetry/status"

DEVICE_IDS = [f"sensor-{i:03d}" for i in range(5)]


def build_metrics_payload(device_id: str) -> dict:
    """Numeric-heavy payload: floats and an int flag."""
    return {
        "device_id": device_id,
        "temperature": round(random.uniform(18.0, 32.0), 2),
        "humidity": round(random.uniform(35.0, 65.0), 2),
        "battery": round(random.uniform(0.0, 100.0), 2),
        "alert": random.choice([0, 1]),
    }


def build_status_payload(device_id: str) -> dict:
    """String/enum-heavy payload: mixed types, distinct shape from metrics."""
    return {
        "device_id": device_id,
        "connection": random.choice(["online", "offline", "degraded"]),
        "firmware_version": f"v{random.randint(1, 3)}.{random.randint(0, 9)}",
        "uptime_seconds": random.randint(0, 86_400),
    }


def publish_forever() -> None:
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    logger.info("Connected to %s:%s, publishing every %ss", BROKER_HOST, BROKER_PORT, PUBLISH_INTERVAL_SECONDS)

    try:
        while True:
            for device_id in DEVICE_IDS:
                client.publish(METRICS_TOPIC, json.dumps(build_metrics_payload(device_id)))
                # Status changes far less often than metrics.
                if random.random() < 0.2:
                    client.publish(STATUS_TOPIC, json.dumps(build_status_payload(device_id)))
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    publish_forever()
