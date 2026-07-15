"""Simulates solar farm telemetry across 3 panel arrays and pushes it to
one or more http_listener_v2 endpoints. Part of the demo showcase; not
part of the application itself.

Unlike apiary_publisher/manufacturing_publisher (which connect out to a
fixed, statically-named broker that fans a single publish out to every
consumer on its own), http_listener_v2 is a plain point-to-point push
target with no broker in between -- so this module takes a *list* of
target URLs (the Collector's own, plus any Automater's that also needs
the same data) and pushes every payload to each of them. See seed.py's
_solar_http_target_urls for why more than one target is needed at all.
"""

import logging
import os
import random
import time

import requests

logger = logging.getLogger("solar_publisher")

PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "20"))

ARRAYS = ["array-1", "array-2", "array-3"]


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


class ArrayMetrics:
    def __init__(self) -> None:
        # cloud_cover is the shared factor irradiance/power_output both
        # derive from in step() below, so the dual-axis panel shows a
        # believable relationship instead of two independently-random
        # lines. A long, rare excursion (vs. the ~8-25 tick default used
        # elsewhere) models a sustained cloudy stretch long enough to
        # actually drag the underperformance Rule's 6h rolling average
        # down, not just a brief dip.
        self.cloud_cover = DriftingMetric(
            0.15, 0.03, 0.05, 0.0, 0.95,
            excursion_target=0.85, excursion_chance=0.01, excursion_duration_range=(90, 300),
        )
        self.panel_temp_c = DriftingMetric(42.0, 0.6, 0.06, 20.0, 90.0, excursion_target=72.0)
        self.inverter_efficiency_pct = DriftingMetric(96.0, 0.3, 0.05, 60.0, 99.0, excursion_target=75.0)
        self.dc_voltage = DriftingMetric(380.0, 2.0, 0.05, 300.0, 420.0, excursion_target=340.0)

    def step(self) -> dict:
        cloud = self.cloud_cover.step()
        irradiance = round(_clamp(950.0 * (1 - cloud) + random.uniform(-15, 15), 0.0, 1100.0), 2)
        power_output = round(_clamp(irradiance * 0.0055 + random.uniform(-0.1, 0.1), 0.0, 6.5), 2)
        return {
            "irradiance_w_m2": irradiance,
            "power_output_kw": power_output,
            "panel_temp_c": self.panel_temp_c.step(),
            "inverter_efficiency_pct": self.inverter_efficiency_pct.step(),
            "dc_voltage": self.dc_voltage.step(),
        }


def _build_payload(array_id: str, metrics: ArrayMetrics) -> dict:
    return {"panel_array_id": array_id, **metrics.step()}


def publish_forever(target_urls: list[str]) -> None:
    logger.info("Pushing to %s every %ss", target_urls, PUBLISH_INTERVAL_SECONDS)
    states = {array_id: ArrayMetrics() for array_id in ARRAYS}

    while True:
        for array_id in ARRAYS:
            payload = _build_payload(array_id, states[array_id])
            for target_url in target_urls:
                try:
                    requests.post(target_url, json=payload, timeout=5)
                except requests.RequestException as exc:
                    # Expected for a while at startup -- the Collector/
                    # Automater container takes a few seconds to deploy
                    # after seed.py provisions it.
                    logger.info("push to %s failed (not up yet?): %s", target_url, exc)
        time.sleep(PUBLISH_INTERVAL_SECONDS)
