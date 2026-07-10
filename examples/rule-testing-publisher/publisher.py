"""Publishes synthetic telemetry to a dedicated rule-testing Collector so
every Automater rule-condition scenario (tag, numeric field, string field,
mixed AND/OR chains) has real data to fire against. Not part of the
application; a manual verification tool. See README.md.
"""

import json
import logging
import math
import os
import random
import time

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rule_testing_publisher")

BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "mosquitto")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "3"))

ENV_TOPIC = "ruletest/env"
DEVICE_TOPIC = "ruletest/device"

SENSORS = [(f"env-{i:02d}", zone) for i, zone in enumerate(["north", "north", "south", "south"], start=1)]
DEVICES = [(f"dev-{i:02d}", loc) for i, loc in enumerate(["rack-1", "rack-1", "rack-2", "rack-2"], start=1)]

# Slow per-sensor phase offsets so each oscillates independently around the
# threshold a test rule would likely use (temperature > 30, battery < 20),
# giving repeated match/clear crossings instead of a static always-true or
# always-false value.
_start = time.time()


def build_env_payload(sensor_id: str, zone: str) -> dict:
    t = time.time() - _start
    phase = hash(sensor_id) % 100 / 100 * math.tau
    temperature = round(30.0 + 4.0 * math.sin(t / 20 + phase) + random.uniform(-0.3, 0.3), 2)
    pressure = round(1013.0 + random.uniform(-8.0, 8.0), 2)
    return {
        "sensor_id": sensor_id,
        "zone": zone,
        "temperature": temperature,
        "pressure": pressure,
        # Plain JSON string field (not a tag) -- exercises string-field
        # ==/!= conditions distinct from tag-based ones.
        "mode": "manual" if random.random() < 0.15 else "auto",
    }


def build_device_payload(device_id: str, location: str) -> dict:
    t = time.time() - _start
    phase = hash(device_id) % 100 / 100 * math.tau
    battery_pct = round(20.0 + 15.0 * math.sin(t / 25 + phase) + random.uniform(-1.0, 1.0), 2)
    rssi = random.randint(-90, -30)
    state = random.choices(["healthy", "degraded", "critical"], weights=[0.7, 0.2, 0.1])[0]
    return {
        "device_id": device_id,
        "location": location,
        "battery_pct": battery_pct,
        "rssi": rssi,
        "state": state,
    }


def publish_forever() -> None:
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    logger.info("Connected to %s:%s, publishing every %ss", BROKER_HOST, BROKER_PORT, PUBLISH_INTERVAL_SECONDS)

    try:
        while True:
            for sensor_id, zone in SENSORS:
                client.publish(ENV_TOPIC, json.dumps(build_env_payload(sensor_id, zone)))
            for device_id, location in DEVICES:
                client.publish(DEVICE_TOPIC, json.dumps(build_device_payload(device_id, location)))
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    publish_forever()
