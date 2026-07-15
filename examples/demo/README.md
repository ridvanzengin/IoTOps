# Demo Showcase

Three curated demo projects, one per data source kind, provisioned and
kept continuously live by this container -- the content behind the public
read-only demo (see `iotops-workspace/ROADMAP.md`'s demo-mode notes).

```
docker compose --profile demo up -d
```

Waits ~10-15s on first run for the backend/Mongo/TimescaleDB to be ready,
then provisions all three projects (idempotent by name -- safe to restart)
and starts publishing.

## Apiary Monitoring Demo (MQTT)

Two MQTT topics (`demo/hive/environment`, `demo/hive/weight`) feeding two
tables on one Collector, across 6 hives. `high-hive-temperature` (real-time
Rule) fires on a temperature spike; `swarm-risk` (Scheduled Query Rule)
fires on the cross-table combination of elevated temperature and a recent
weight drop -- real-time Rules are single-table only, so this is the one
scenario that genuinely needs the Query Rule engine's cross-table SQL.

## Solar Farm Demo (HTTP)

`http_listener_v2` has no broker -- a plain point-to-point push target, not
pub/sub. Once `panel-overheating` derives an Automater listening on the
same table, the publisher must push every payload to *both* the
Collector's and the Automater's container, or the second listener never
sees data (same gap `data-sources-showcase`'s own `http_publisher.py`
already documents). `underperformance` (Scheduled Query Rule) is the
contrast case: a 6h rolling-average degradation signal a point-in-time
real-time Rule can't express.

## Manufacturing Line Demo (Kafka)

Kafka consumer-group semantics are competing-consumer, not broadcast --
already handled generically by `AutomaterService._automater_scoped_configuration`
(same fix `data-sources-showcase` needed). `rpm-drift` (Scheduled Query
Rule) combines two aggregates (`AND`) over the same table, a different
shape than Apiary's cross-table join.

## Data generation

Every metric is a small mean-reverting random walk with randomly-timed,
randomly-lasting excursions toward an alert-range target (see each
publisher's `DriftingMetric` class) -- deliberately not a fixed-period sine
wave, so the charts don't look like an obviously repeating pattern. Real
threshold crossings still happen, just at random offsets per entity.

Stop with `docker compose --profile demo down` (leaves `mosquitto`/`kafka`
running, same as the other showcases, since they have no `profiles:` key
of their own or are shared with `data-sources`).
