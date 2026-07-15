"""Simulates manufacturing line telemetry across 3 machines and publishes
it to Kafka. Part of the demo showcase; not part of the application
itself.
"""

import json
import logging
import os
import random
import time

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

logger = logging.getLogger("manufacturing_publisher")

KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = "manufacturing.line.telemetry"
PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "20"))

MACHINES = ["cnc-01", "cnc-02", "press-03"]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class DriftingMetric:
    """Mean-reverting random walk with randomly-timed, randomly-lasting
    excursions -- see apiary_publisher.py's copy of this class for the
    full rationale (avoids a fixed-period sine wave's too-regular look)."""

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


class MachineMetrics:
    def __init__(self) -> None:
        self.vibration_rms = DriftingMetric(4.5, 0.15, 0.07, 0.5, 12.0, excursion_target=9.0)
        # rpm/motor_temp_c derive from this shared "under strain" factor
        # (see step() below) so rpm-drift's AND(rpm-out-of-band,
        # temp-elevated) condition is a real compound signal, not two
        # independently-random fields that happen to line up by chance.
        self.strain = DriftingMetric(
            0.0, 0.03, 0.04, 0.0, 1.0,
            excursion_target=0.9, excursion_chance=0.02, excursion_duration_range=(15, 40),
        )
        self.current_draw_amps = DriftingMetric(18.0, 0.4, 0.06, 5.0, 40.0, excursion_target=32.0)
        self.oil_pressure_psi = DriftingMetric(45.0, 0.5, 0.05, 10.0, 70.0, excursion_target=20.0)

    def step(self) -> dict:
        strain = self.strain.step()
        rpm = round(_clamp(2000.0 + strain * 500.0 + random.uniform(-40, 40), 500.0, 3000.0), 0)
        motor_temp_c = round(_clamp(70.0 + strain * 25.0 + random.uniform(-2, 2), 30.0, 120.0), 2)
        return {
            "vibration_rms": self.vibration_rms.step(),
            "rpm": rpm,
            "motor_temp_c": motor_temp_c,
            "current_draw_amps": self.current_draw_amps.step(),
            "oil_pressure_psi": self.oil_pressure_psi.step(),
        }


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

    states = {machine_id: MachineMetrics() for machine_id in MACHINES}

    try:
        while True:
            for machine_id in MACHINES:
                payload = {"machine_id": machine_id, **states[machine_id].step()}
                producer.send(KAFKA_TOPIC, payload)
            producer.flush()
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    finally:
        producer.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    publish_forever()
