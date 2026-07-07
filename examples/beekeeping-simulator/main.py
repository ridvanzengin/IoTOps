"""Entrypoint for the Beekeeping Showcase demo container: provisions the
Project/Collector/Dashboard once, then publishes simulated hive telemetry
forever. See examples/beekeeping-simulator/README.md.
"""

import logging

from seed import ensure_demo_provisioned
from simulator import publish_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    ensure_demo_provisioned()
    publish_forever()
