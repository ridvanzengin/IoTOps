"""Simulates apiary environmental and weight telemetry across 6 hives and
publishes it to two separate MQTT topics (one table each). Part of the
demo showcase (see examples/demo/README.md); not part of the application
itself.
"""

import json
import logging
import os
import random
import time

import paho.mqtt.client as mqtt

logger = logging.getLogger("apiary_publisher")

BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "mosquitto")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "20"))

ENVIRONMENT_TOPIC = "demo/hive/environment"
WEIGHT_TOPIC = "demo/hive/weight"

HIVES = ["hive-a1", "hive-a2", "hive-a3", "hive-b1", "hive-b2", "hive-b3"]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class DriftingMetric:
    """Mean-reverting random walk with randomly-timed, randomly-lasting
    excursions toward `excursion_target` -- avoids the too-regular look of
    a fixed-period sine wave while still producing occasional real
    threshold crossings. Same statistical family as the existing
    beekeeping-simulator's HiveState / data-sources-showcase's
    VehicleState, generalized to any metric. Duplicated per publisher file
    (not a shared module) to match this repo's existing one-file-per-
    concern convention for these example fixtures."""

    def __init__(
        self,
        baseline: float,
        noise_sigma: float,
        reversion_rate: float,
        low: float,
        high: float,
        excursion_target: float,
        excursion_chance: float = 0.03,
        excursion_duration_range: tuple[int, int] = (8, 25),
    ) -> None:
        self.value = baseline
        self.baseline = baseline
        self.noise_sigma = noise_sigma
        self.reversion_rate = reversion_rate
        self.low = low
        self.high = high
        self.excursion_target = excursion_target
        self.excursion_chance = excursion_chance
        self.excursion_duration_range = excursion_duration_range
        self.excursion_ticks_left = 0

    def step(self) -> float:
        target = self.excursion_target if self.excursion_ticks_left > 0 else self.baseline
        self.value += self.reversion_rate * (target - self.value) + random.gauss(0, self.noise_sigma)
        self.value = _clamp(self.value, self.low, self.high)
        if self.excursion_ticks_left > 0:
            self.excursion_ticks_left -= 1
        elif random.random() < self.excursion_chance:
            self.excursion_ticks_left = random.randint(*self.excursion_duration_range)
        return round(self.value, 2)


class HiveMetrics:
    def __init__(self) -> None:
        # Excursion target 41.0 sits comfortably above the
        # high-hive-temperature Rule's 38 threshold (a faster
        # reversion_rate than the other publishers' metrics, 0.12 vs
        # ~0.07-0.08, means each excursion converges past the threshold
        # quickly instead of lingering in the 36-40 flicker zone -- with
        # 6 hives rolling independently each tick, a chance tuned the same
        # as Solar/Manufacturing's 3-entity metrics fired noticeably more
        # often here purely from having double the entities, before this
        # was lowered to compensate). Weight's dips (independently timed)
        # are what swarm-risk's cross-table condition also needs alongside
        # a temperature excursion within the same rolling hour.
        self.temperature = DriftingMetric(
            34.5, 0.15, 0.12, 28.0, 42.0, excursion_target=41.0, excursion_chance=0.015
        )
        self.humidity = DriftingMetric(60.0, 0.5, 0.06, 40.0, 80.0, excursion_target=75.0)
        self.co2_ppm = DriftingMetric(900.0, 15.0, 0.05, 400.0, 2000.0, excursion_target=1600.0)
        self.sound_level_db = DriftingMetric(48.0, 0.8, 0.07, 30.0, 75.0, excursion_target=65.0)
        self.weight_kg = DriftingMetric(
            33.0, 0.03, 0.03, 15.0, 45.0, excursion_target=28.0, excursion_chance=0.02
        )


def publish_forever() -> None:
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    logger.info("Connected to %s:%s, publishing every %ss", BROKER_HOST, BROKER_PORT, PUBLISH_INTERVAL_SECONDS)

    states = {hive_id: HiveMetrics() for hive_id in HIVES}

    try:
        while True:
            for hive_id in HIVES:
                metrics = states[hive_id]
                environment_payload = {
                    "hive_id": hive_id,
                    "temperature": metrics.temperature.step(),
                    "humidity": metrics.humidity.step(),
                    "co2_ppm": metrics.co2_ppm.step(),
                    "sound_level_db": metrics.sound_level_db.step(),
                }
                weight_payload = {"hive_id": hive_id, "weight_kg": metrics.weight_kg.step()}
                client.publish(ENVIRONMENT_TOPIC, json.dumps(environment_payload))
                client.publish(WEIGHT_TOPIC, json.dumps(weight_payload))
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    publish_forever()
