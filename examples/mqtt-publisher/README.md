# MQTT Test Publisher

Manual verification tool for the Collector -> MQTT -> TimescaleDB pipeline
(Milestone 2). Not part of the application.

Publishes synthetic telemetry to two topics with different payload shapes:

- `telemetry/metrics` — numeric-heavy (temperature, humidity, battery as
  floats; alert as an int)
- `telemetry/status` — string/enum-heavy (connection, firmware_version as
  strings; uptime_seconds as an int), published less frequently

## Usage

Off by default. Start it alongside the stack when you want to verify
ingestion:

```
docker compose --profile tools up -d mqtt-publisher
```

Create a Collector (via the UI or API) with an MQTT input per topic —
each needs its own `name_override` so they land in separate tables, and
`json_string_fields` listing any string-valued JSON keys, since Telegraf's
JSON parser silently drops string fields that aren't listed there:

```json
{
  "name": "Pipeline Verification",
  "inputs": [
    {
      "plugin_type": "mqtt",
      "name": "metrics-input",
      "configuration": {
        "topics": ["telemetry/metrics"],
        "name_override": "device_metrics",
        "json_string_fields": ["device_id"]
      }
    },
    {
      "plugin_type": "mqtt",
      "name": "status-input",
      "configuration": {
        "topics": ["telemetry/status"],
        "name_override": "device_status",
        "json_string_fields": ["device_id", "connection", "firmware_version"]
      }
    }
  ],
  "outputs": [{ "plugin_type": "timescaledb", "configuration": {} }]
}
```

Deploy it, then check TimescaleDB:

```
docker exec iotops-timescaledb-1 psql -U iotops -d iotops -c "SELECT * FROM device_metrics ORDER BY time DESC LIMIT 5;"
```

Stop the publisher with `docker compose --profile tools stop mqtt-publisher`.
