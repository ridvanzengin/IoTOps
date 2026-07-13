"""Entrypoint for the Data Sources Showcase demo container: provisions
the Project/Collectors/Rules/Dashboard once, then publishes simulated
telemetry to Kafka, HTTP, and AMQP forever, each on its own thread. See
examples/data-sources-showcase/README.md.
"""

import logging
import threading

import amqp_publisher
import http_publisher
import kafka_publisher
from seed import ensure_demo_provisioned

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    http_target_urls = ensure_demo_provisioned()

    threading.Thread(target=kafka_publisher.publish_forever, daemon=True).start()
    threading.Thread(target=amqp_publisher.publish_forever, daemon=True).start()
    # Runs on the main thread, not a daemon thread -- keeps the container
    # alive the same way beekeeping-simulator's publish_forever() does.
    http_publisher.publish_forever(http_target_urls)
