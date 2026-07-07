# Beekeeping Showcase

The first working, end-to-end demonstration of the platform (Milestone 4):
Collector -> Telemetry -> Dashboard, running against simulated bee hive
telemetry. Not part of the application itself -- a demo, like
`examples/mqtt-publisher/`.

Simulates 2 apiaries x 3 hives (6 hives total), each publishing temperature,
humidity, and weight to `beekeeping/hive` over MQTT. On startup, the
container also provisions a Project, a Collector (MQTT input ->
TimescaleDB output), and a Dashboard against the backend's own REST API --
so unlike `mqtt-publisher`, no manual Collector setup is needed afterward.

## Usage

Off by default, like every demo/tool in `examples/`. One command brings up
the entire stack plus this demo, even from a cold stop -- Compose includes
every service with no `profiles:` key regardless of which profile is
requested:

```
docker compose --profile beekeeping up -d
```

Wait ~10-15 seconds for the Collector to deploy and ingest its first rows,
then open the "Beekeeping Overview" dashboard from the Dashboards nav. The
Apiary dropdown filters the Hive dropdown (a chained/predicate variable
pair); switching Apiary changes which hives are selectable. Five panels:
Hive Temperature, Hive Humidity, Hive Weight (all filtered by the selected
Apiary + Hive), Apiary Hives Temperature (filtered by Apiary only, split
into one line per hive in that apiary via the long-format `series_by` chart
feature), and All Hives Weight (no variable filter at all -- always all 6
hives across both apiaries, one line each).

Re-running `docker compose --profile beekeeping up -d` (or a container
restart) is safe -- the Project/Collector/Dashboard are looked up by name
and reused rather than duplicated.

Check ingestion directly if needed:

```
docker exec iotops-timescaledb-1 psql -U iotops -d iotops -c "SELECT * FROM hive_metrics ORDER BY time DESC LIMIT 5;"
```

Stop the demo with `docker compose --profile beekeeping down`.
