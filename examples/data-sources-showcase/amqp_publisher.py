"""Publishes synthetic delivery-fleet telemetry to RabbitMQ. Part of the
Data Sources Showcase; not part of the application itself -- see
examples/data-sources-showcase/README.md.
"""

import json
import logging
import os
import random
import time

import pika

logger = logging.getLogger("amqp_publisher")

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
EXCHANGE = "fleet.telemetry"
PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "3"))

VEHICLES = [
    {"vehicle_id": "van-01", "route": "north-loop"},
    {"vehicle_id": "van-02", "route": "south-loop"},
    {"vehicle_id": "van-03", "route": "downtown"},
]


class VehicleState:
    """Fuel drains gradually and jumps back up on an occasional refuel --
    same gentle-drift-with-a-reset shape as the beekeeping simulator's
    hive weight, so a low-fuel rule repeatedly matches/clears instead of
    firing once and going stale."""

    def __init__(self) -> None:
        self.fuel_pct = round(random.uniform(60.0, 100.0), 2)

    def step(self) -> dict:
        self.fuel_pct -= random.uniform(0.5, 2.5)
        if self.fuel_pct < 5.0:
            self.fuel_pct = round(random.uniform(85.0, 100.0), 2)  # refuel
        speed_kmh = round(random.uniform(20.0, 90.0), 2)
        return {"fuel_pct": round(self.fuel_pct, 2), "speed_kmh": speed_kmh}


def _connect() -> pika.BlockingConnection:
    attempt = 0
    while True:
        try:
            return pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, heartbeat=30))
        except pika.exceptions.AMQPConnectionError as exc:
            attempt += 1
            logger.info("RabbitMQ not ready yet (attempt %s): %s", attempt, exc)
            time.sleep(3)


def publish_forever() -> None:
    connection = _connect()
    channel = connection.channel()
    # exchange_type must match the Collector's amqp input config
    # (exchange_type defaults to "topic" -- see AmqpConsumerConfig).
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    logger.info("Connected to RabbitMQ at %s, publishing every %ss", RABBITMQ_HOST, PUBLISH_INTERVAL_SECONDS)

    states = {vehicle["vehicle_id"]: VehicleState() for vehicle in VEHICLES}

    try:
        while True:
            for vehicle in VEHICLES:
                payload = {**vehicle, **states[vehicle["vehicle_id"]].step()}
                # binding_key="#" on the Collector's amqp input matches any
                # routing key on a topic exchange, so the exact key here
                # doesn't need to line up with anything specific.
                channel.basic_publish(exchange=EXCHANGE, routing_key="fleet.telemetry", body=json.dumps(payload))
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    finally:
        connection.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    publish_forever()
