"""Entrypoint for the demo showcase container: provisions the 3 demo
projects (Apiary/MQTT, Solar/HTTP, Manufacturing/Kafka) once, then
publishes simulated telemetry to all three forever, each on its own
thread. See examples/demo/README.md.
"""

import logging
import threading

import apiary_publisher
import manufacturing_publisher
import solar_publisher
from seed import ensure_demo_provisioned

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    solar_target_urls = ensure_demo_provisioned()

    threading.Thread(target=apiary_publisher.publish_forever, daemon=True).start()
    threading.Thread(target=manufacturing_publisher.publish_forever, daemon=True).start()
    # Runs on the main thread, not a daemon thread -- keeps the container
    # alive the same way beekeeping-simulator's publish_forever() does.
    solar_publisher.publish_forever(solar_target_urls)
