# Data Sources Showcase

Demonstrates the non-MQTT Collector input plugins (`kafka`, `http`,
`amqp` -- see `app/plugin/inputs/`) end to end, the same way
`beekeeping-simulator` demonstrates the original `mqtt` one. Not part of
the application itself.

On startup, the container provisions (idempotently, by name -- safe to
restart) a Project, two Collectors, three Rules, and a Dashboard against
the backend's own REST API, then publishes simulated telemetry forever:

- **Factory Floor Kafka Collector** -- one `kafka` input, topic
  `factory.machines`, three simulated machines (`press-01`, `press-02`,
  `lathe-01`) oscillating `vibration_mm_s` around the `high-vibration`
  rule's threshold (`> 9.0`). Table: `kafka_metrics`.
- **Web & Queue Collector** -- two inputs in one Collector/Telegraf
  process:
  - `http` (webhook push): three simulated weather stations (`wx-01/02/03`)
    oscillating `wind_speed_kmh` around the `high-wind` rule's threshold
    (`> 40.0`). Table: `http_metrics`.
  - `amqp`: three simulated delivery vehicles (`van-01/02/03`) with
    `fuel_pct` draining and occasionally refueling, around the
    `low-fuel` rule's threshold (`< 15.0`). Table: `amqp_metrics`.

**Data Sources Overview** dashboard has one panel per table, each split
into one line per entity (`series_by`).

Building and verifying this against the real stack surfaced three real
bugs (two fixed, one documented as a known gap) that unit tests hadn't
caught -- see `iotops-workspace/ROADMAP.md`'s "Follow-up 2026-07-13"
note for the full story. The most significant: `custom-telegraf`'s
`processors/rule` was leaking every metric's tracking reference (fixed
in `rule.go`'s `Apply()`), which stalled an Automater watching an
amqp-sourced table within seconds of hitting RabbitMQ's default
`prefetch_count` of 50 -- this showcase is what surfaced it, since
nothing had run an Automater against AMQP (or Kafka for long enough)
before.

## A note on Kafka consumer groups / AMQP queues

Unlike MQTT (true broadcast pub/sub), Kafka consumer groups and AMQP
queues are *competing*-consumer patterns by default -- two consumers on
the same group/queue split messages between them rather than each
getting a full copy. The Automater's derived input (a second Telegraf
process, evaluating rules independently of the Collector's own
ingestion) needed its own consumer_group/queue, distinct from the
Collector's, to get an independent full copy of the same stream --
already handled automatically by `AutomaterService
._automater_scoped_configuration`; nothing this showcase's Collectors do
needs to account for it.

## A note on HTTP push having no broker

Kafka/AMQP/MQTT all fan a single publish out to every independent
consumer via a broker; `http_listener_v2` has no broker at all -- it's a
plain point-to-point push target. The Collector's and Automater's
`http_listener_v2` instances are two unrelated listeners in two separate
containers, so whoever's pushing has to push to *both* explicitly, or
only the first one ever sees any data (this is exactly what happened the
first time this showcase was built and verified -- the Kafka/AMQP rules
fired immediately, `high-wind` never did, until `http_publisher.py` was
changed to push to every target `seed.py` resolves, not just the
Collector's). `seed.py`'s `_http_target_urls` looks up every Automater
currently covering `http_metrics` and this publisher pushes to all of
them. This is a genuine architectural gap specific to push-based inputs
-- not something a real external webhook source (which only ever pushes
to one configured URL) can work around the way this demo's own publisher
does. See `iotops-workspace/ROADMAP.md`'s data-sources entry for the
real fix this points at (the Automater deploy path reusing the
Collector's own listener process for push-based plugin types, instead of
spinning up a second, separately-unreachable one).

## Usage

Off by default, like every demo in `examples/`. One command brings up
the entire stack plus this demo, even from a cold stop:

```
docker compose --profile data-sources up -d
```

This also brings up `kafka` and `rabbitmq` (declared with no `profiles:`
key in `docker-compose.yml`, so every profile includes them) -- Kafka
takes a few seconds to finish its KRaft startup, RabbitMQ has a
management UI at http://localhost:15672 (guest/guest) if you want to
watch exchanges/queues directly. Kafka is reachable from the host at
`localhost:9094` if you want to point your own client tooling at it (the
in-container/publisher traffic uses `kafka:9092`, a separate listener --
see `docker-compose.yml`'s own comment on why).

Wait ~15-20 seconds for both Collectors to deploy and start ingesting,
then open the "Data Sources Overview" dashboard, or watch the
"Data Sources Showcase" project's Events sidebar for `high-vibration` /
`high-wind` / `low-fuel` firing as the simulated values cross their
thresholds.

Check ingestion directly if needed:

```
docker exec iotops-timescaledb-1 psql -U iotops -d iotops -c "SELECT * FROM kafka_metrics ORDER BY time DESC LIMIT 5;"
docker exec iotops-timescaledb-1 psql -U iotops -d iotops -c "SELECT * FROM http_metrics ORDER BY time DESC LIMIT 5;"
docker exec iotops-timescaledb-1 psql -U iotops -d iotops -c "SELECT * FROM amqp_metrics ORDER BY time DESC LIMIT 5;"
```

Stop the demo (keeps kafka/rabbitmq running, since they have no
`profiles:` key) with:

```
docker compose --profile data-sources stop data-sources-showcase
```
