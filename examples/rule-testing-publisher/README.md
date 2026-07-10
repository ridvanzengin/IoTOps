# Rule Testing Publisher

Manual verification tool for exercising every Automater rule-condition
scenario against real data: tag-based conditions, numeric-field
conditions, string-field conditions, and mixed AND/OR chains. Not part of
the application. Companion to the "Rule Testing Sandbox" project /
"Rule Testing Collector" (already created via the API, not by this tool).

Publishes synthetic telemetry to two topics with different payload shapes:

- `ruletest/env` — `env_readings` table. Tags: `sensor_id`, `zone`.
  Numeric fields: `temperature` (oscillates around 30.0, so a rule like
  `temperature > 30` repeatedly matches/clears), `pressure`. String field
  (not a tag — exercises Telegraf's `json_string_fields`, distinct from a
  tag-based condition): `mode` (`"auto"` / `"manual"`).
- `ruletest/device` — `device_health` table. Tags: `device_id`,
  `location`. Numeric fields: `battery_pct` (oscillates around 20.0),
  `rssi`. String field: `state` (`"healthy"` / `"degraded"` /
  `"critical"`).

## Usage

Off by default. Start it alongside the stack when you want live data:

```
docker compose --profile tools up -d rule-testing-publisher
```

The Collector (`Rule Testing Collector`, in the `Rule Testing Sandbox`
project) already has both mqtt inputs configured with the matching
`name_override`/`tag_keys`/`json_string_fields` for these two topics —
deploy it and this publisher's data starts flowing into `env_readings`
and `device_health` immediately.

Check TimescaleDB directly:

```
docker exec iotops-timescaledb-1 psql -U iotops -d iotops -c "SELECT * FROM env_readings ORDER BY time DESC LIMIT 5;"
docker exec iotops-timescaledb-1 psql -U iotops -d iotops -c "SELECT * FROM device_health ORDER BY time DESC LIMIT 5;"
```

Stop it with `docker compose --profile tools stop rule-testing-publisher`.
