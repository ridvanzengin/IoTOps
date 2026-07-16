# Changelog

Dated, compressed history of what's actually shipped, across both this
repo and [custom-telegraf](https://github.com/ridvanzengin/custom-telegraf)
(IoTOps's sibling Go repo — entries below note when a change spans both).
For current status and what's still open, see
[docs/development-plan.md](docs/development-plan.md).

Newest first. Each entry is a compressed summary, not a full narrative —
where a bug fix taught something worth remembering (a real footgun, not
just "fixed a typo"), that's kept; blow-by-blow debugging steps aren't.

## 2026-07-16

**IoTOps is live at https://iotops.online.** Deployed on the shared
Hetzner VM ("ringo") alongside AgriTwin, reusing its `infra` project
(nginx/TimescaleDB/Redis) rather than standing up new infrastructure —
see `deploy/SERVER_SETUP.md`. `DEMO=true` (read-only); all 3 demo
scenarios (Apiary/MQTT, Solar/HTTP, Manufacturing/Kafka) work end to end,
Kafka included from the start of this entry (it was launched without it
first, added once the rest of the stack had run stably for a while).

Standing this up for real (not just planning it) surfaced real bugs no
amount of re-reading the plan would have caught:
- `timescaledb.py`'s hardcoded connection host doesn't resolve on the
  shared VM; `npm run build` had never actually been run before (no CI)
  and had real `tsc` errors.
- The shared `infra-nginx-1` can silently stop listening on 80/443
  (workers alive, nothing bound) after several containers join its
  network in quick succession — needs a plain restart, `nginx -s reload`
  doesn't fix it. Also: a bare `proxy_pass http://host:port` caches the
  target's IP at nginx startup/reload *indefinitely* — only the `set
  $upstream ...; proxy_pass $upstream;` form actually respects a
  `resolver ... valid=30s` directive, so every redeploy that recreates a
  container needs that form or it silently 502s until someone manually
  reloads nginx.
- `infra-db-1`'s `max_connections=25`, shared with AgriTwin, couldn't fit
  asyncpg's own default pool size (min=10/max=10) — capped explicitly.
- `examples/demo/seed.py`'s one-time provisioning got 403'd by its own
  `DEMO=true` from first boot; fixed with a narrowly-scoped
  `X-Demo-Seed-Token` bypass on just the create/update routes it touches,
  not a manual "flip DEMO off, reseed, flip back on" dance.
- `custom-telegraf` was never built on the VM at all (undocumented until
  now); combined with the seed-token fix's retry loop, a failed Automater
  deploy left an orphaned Mongo record and a stale Collector
  `http_forward` output on every retry instead of erroring cleanly —
  `AutomaterService.create_rule()` now defers that side effect until
  deploy actually succeeds, and rolls back a just-created Automater if it
  doesn't.
- `seed.py`'s Solar HTTP target-URL builder used the wrong container
  hostname convention (`iotops-collector-{full-uuid}` instead of
  `iotops-{collector,automater}-{name-slug}-{short-id}`) — the Solar demo
  scenario had never actually reached its targets, in any environment,
  before this was caught.
- `deploy.sh` hardcoded `git pull origin main` instead of pulling
  whatever branch is actually checked out — silently no-op'd on a
  deploy, which cascaded into duplicate seeded projects/dashboards from
  stale code before it was caught and cleaned up.

Also: `examples/demo/seed.py`'s project names and dashboard panels now
match hand-edits made in the local dev environment (renamed
projects, alert overlays consolidated onto the real data panels instead
of separate "(with Alerts)" duplicates, two new panels surfacing metrics
the publishers already produced but never showed). Added a `/deploy`
skill (`.claude/skills/deploy/SKILL.md`) capturing the routine-update
flow and all of the above as a troubleshooting playbook, so the next
session starts from this instead of rediscovering it.

## 2026-07-14

**Events sidebar: consistent counts, time range, search, pagination.**
Three previously-independent count sources (ActivityBar badge, per-rule
filter chips, rendered cards) collapsed into one shared server-side query
(`EventRepository._query_occurrences`), so a chip's count and what
clicking it loads can no longer structurally disagree. Added a time-range
selector (default last 1h) and a search box (rule name/message/category/
event type **and** identifier keys/values) to the Events panel, plus real
pagination (20/page). The ActivityBar's own badge deliberately stays
unbounded by time ("currently unresolved, regardless of age") — see
2026-07-16's follow-up fix, which closed the gap this created (the panel
had no way to ever reach an occurrence older than its widest range).
Live updates switched from incremental client-side patching to a
debounced refetch of ground truth on any relevant SSE event.

**Query Rules — scheduled, SQL-based event detection alongside real-time
Rules.** A second kind of Rule for checks the real-time, single-table,
per-metric Go pipeline can't express: cross-table joins, time-windowed
aggregates, arbitrary AND/OR nesting. Modeled as a scheduled analytical
query, not force-fit into the streaming pipeline:
- Condition is raw SQL (validated via the existing `validate_select_only_sql`
  guard, same one already used for the AI SQL builder and Panel queries),
  not a structured expression tree — TimescaleDB already is the
  aggregate/boolean engine this needs.
- Evaluated via Celery Beat on the rule's own configurable interval/cron
  (new `app/query_rule/` module, `croniter` dependency), sharing the
  existing `celery-worker` process with real-time matches — confirmed
  safe under load via a deliberate 15s `pg_sleep` timeout test.
- Reuses the entire downstream Events pipeline unmodified (`Occurrence`
  pairing, SSE delivery, Panel overlays, manual-resolve) via a new
  `source_type` discriminator on `Event`/`Occurrence`.
- Natural-language authoring reuses `AiService` (same Ollama connection,
  schema-aware prompting) already built for the Dashboard SQL builder.
- New frontend: `QueryRuleEditor`/`QueryRuleList` pages, a two-card
  "Real-time vs. Scheduled" chooser at rule-creation time, `NlSqlBuilder`
  extracted out of `PanelBuilder` for reuse.

## 2026-07-13

**HTTP data-source fan-out fixed.** Broker-mediated sources (MQTT/Kafka/
AMQP) fan one publish out to every independent subscriber for free; a
plain webhook (`http_listener_v2`) has no broker, so an Automater's
"independent instance" was a second, unreachable listener nothing ever
pushed to. Fixed by having the Collector forward a copy of what it
receives to the Automater's own listener via a new `[[outputs.http]]`
block (`http_forward` plugin), added automatically when an http-sourced
Rule is created and removed when the Automater is deleted. Two real bugs
found via live verification, not unit tests: Go's `net/http.Server` falls
back to `ReadTimeout` as its idle keep-alive timeout when `IdleTimeout`
isn't set, which raced against this platform's fixed flush interval
(fixed: bumped forwarding timeouts to 60s); and a JSON-format forwarding
config produced well-formed-but-empty metrics with no error anywhere
(Telegraf's output JSON and input JSON parser are non-interoperable
shapes — fixed by forwarding as `influx` line protocol instead).

**Kafka, HTTP, and AMQP data sources added**, alongside the original
MQTT — three new input plugins, zero Go changes needed (the custom
Telegraf image already embedded upstream's `kafka_consumer`/
`http_listener_v2`/`amqp_consumer`, just never registered on the IoTOps
side). Automater's MQTT-only assumptions generalized across both repos.
Building a `data-sources-showcase` fixture to exercise these surfaced
three real, previously-latent bugs:
1. **Competing-consumer bug**: Kafka consumer groups and AMQP queues
   *split* messages across same-group/same-queue consumers (unlike MQTT's
   broadcast pub/sub) — an Automater deriving its input verbatim from a
   Collector's config would have silently shared the stream 50/50 with
   it. Fixed by scoping the Automater's `consumer_group`/`queue` to a
   distinct value.
2. `processors/rule` (Go) was leaking a tracking-metric reference on
   *every* `Apply()` call, matched or not — invisible on MQTT (QoS 0, no
   ack required) and slow to surface on Kafka (high default undelivered-
   message ceiling), but hit AMQP's low default `prefetch_count`
   immediately, wedging delivery once the leak backlog filled it. Fixed:
   `Apply()` now calls `m.Drop()` unconditionally once per input metric.

**Event resolution mode: auto-clear vs. manual-resolve.** Every Rule
gained a `resolve_mode` (auto, default, or manual). A manual-resolve
Rule's occurrence never auto-clears — it stays Active until a human
resolves it from the sidebar with an optional note. Flows cross-repo:
`Rule.resolve_mode` → generated TOML → `rule.go`'s `RuleConfig.ResolveMode`,
which skips `clearFiring()` entirely for manual-resolve rules so the
Redis firing key isn't cleared out from under a still-open occurrence.

**Events overlay directly on Panel charts.** A panel can now show a
multi-select of specific Rules as markers on its own chart — plotted as
shaped/colored scatter points on a dedicated hidden `[0,1]`-fixed
secondary axis (keeps markers in one consistent band regardless of what
the real data is doing), filtered by whatever dashboard variables are
currently resolved.

**Occurrence card identifiers are clickable**, setting the matching
dashboard variable(s) — applies an occurrence's whole identifier set at
once (not one field at a time), in dependency order, so a cascading
variable's options re-resolve correctly against a just-changed parent
variable in the same click.

## 2026-07-11

**Events sidebar redesigned around a persistent activity bar** (VSCode-
style): one icon per Project plus one for Co-pilot, reachable from every
page (previously the sidebar only existed embedded per-Dashboard). Each
project's icon carries a live unresolved-match badge. One persistent SSE
connection for the whole session (previously reopened per dashboard
visit), switched to `PSUBSCRIBE events:*` so a single stream feeds every
project's badge plus whichever panel is open. Occurrence cards redesigned
(severity-colored border, Active/Resolved status pill, identifier chips,
expandable detail drawer) and switched from a flat raw-event log to
paired occurrences (one row per match+clear, not two).

## 2026-07-10

**Events sidebar + persisted event store shipped for the first time** —
previously `log_rule_match` only logged to stdout. New Mongo-backed
`Event` model, live SSE delivery to a project-scoped sidebar. Required a
cross-repo attribution fix first: matched events carried a rule *name*
but no `rule_id`/`automater_id`/`project_id`, so nothing could attribute
an event back to a project — added to `rule.go`'s stamped tags and a new
`DeployedRule` model on the IoTOps side.

**Multi-table Automaters.** An Automater can now watch more than one
table (gains a new mqtt input, derived from a chosen Collector, the first
time a rule needs a table it doesn't already cover) — found via a real
bug where attaching a second rule on a different table to an existing
single-table Automater silently pre-filled dedup identifiers from the
*wrong* table and would have deployed a rule that could never fire.

**Automater/Rule architecture redesign.** Automater = a deployed service
(a project can have as many as it wants, mirroring Collector); Rule = an
independently addressable resource with its own lifecycle
(activate/deactivate/delete), living inside one Automater. Previously the
frontend always created a brand-new Automater with no lookup for an
existing one, so two rules meant for the same automation setup ended up
as two separate deployed containers.

**Per-condition AND/OR chains.** `Rule.operator` (one operator for the
whole rule) replaced with `Condition.join` (each condition joins to the
*previous* one), enabling genuinely mixed chains like
`a==1 AND b>3 OR c<5`, evaluated as a strict left-to-right fold (no
precedence/parentheses). Also fixed: condition evaluation only ever
checked metric *fields*, never *tags* — a condition on a tag-typed column
always evaluated false regardless of the real value.

**First automated tests, both repos** — previously zero. `custom-telegraf`:
`rule_test.go` (pure functions) plus `miniredis`-backed integration tests.
IoTOps: `tests/backend/automater/`, which also caught 7 pre-existing
`collector`/`plugin` tests that had silently rotted (broken imports after
an earlier refactor, never re-run).

## 2026-07-09

**Match/clear firing semantics.** Rules now emit a `match` tag on first
trip and a `clear` tag when the condition stops holding, using the
existing Redis dedup key repurposed into a firing-state key
(`SETNX`/`DEL` instead of a one-shot TTL suppression window).

**Every enabled rule evaluated independently**, not first-match-wins —
reversed same day after real usage showed two unrelated rules on the same
table (temperature + humidity) both needed to fire, not compete.

**Rule firing keys scoped by rule ID, not name** — rule names were never
enforced unique, so two same-named rules (even across unrelated
Automaters) would have silently shared firing/dedup state.

## 2026-07-08

**Automation Engine core shipped, end-to-end.** `custom-telegraf` gained
real logic in `processors/rule` (AND/OR condition evaluation, Redis
dedup, tag/message stamping) and `outputs/celery` (a real Celery
protocol-v2 envelope, consumable by an unmodified Python `celery`
worker) — the two custom Go plugins this whole engine depends on. IoTOps
gained the `Automater` backend module (`app/automater/`, mirroring
`Collector`'s shape) and frontend (single-page rule-creation form with a
schema-driven condition builder, replacing an originally-planned
multi-step wizard). Verified against the real stack: an MQTT message
crossing a rule's threshold flowed through Go's rule evaluation, Redis
dedup, the Celery envelope, and into a real Python worker's logs.

## v1 — Core Platform (Milestones 0–4)

Predates day-by-day tracking above. Summarized from the original
milestone plan.

- **Repository bootstrap**: FastAPI + React/TS/Vite skeleton, Docker
  Compose (MongoDB, TimescaleDB, Mosquitto, Redis), health endpoints.
- **Collector management**: plugin registry pairing a typed Pydantic
  config model per Telegraf plugin; a schema-driven 4-step creation
  wizard with no per-plugin hardcoded forms; Docker-outside-of-Docker
  lifecycle management for spawned Telegraf containers.
- **Telemetry pipeline**: MQTT → Telegraf → TimescaleDB, with the output
  plugin's `create_templates` producing real hypertables automatically
  (no manual schema-migration step). Several real Telegraf-version-
  specific config gotchas found and fixed at the model-default level
  (wrong template variable names, JSON parser silently dropping
  unlisted string fields) — see `app/plugin/outputs/timescaledb.py`'s
  comments for detail, since these would otherwise resurface as data
  loss for any new user hand-configuring a plugin.
- **Dashboard system**: Project as the root grouping entity; Panel/Chart
  models over Apache ECharts; a Grafana-style `$__timeFrom`/`$__timeTo`
  macro system for time-range-aware queries; cascading Variable Builder
  (schema-driven, no free-typed SQL); dual-axis and long-format
  ("melted"/tidy, via `series_by`) chart rendering; dashboard
  auto-refresh. A narrow slice of the AI milestone was pulled forward
  here: `POST /api/ai/sql`, an Ollama-backed natural-language SQL
  builder — by design, the only way to author Panel SQL at all (no
  visual query builder was ever built).
- **Beekeeping showcase**: a self-provisioning MQTT simulator (2
  apiaries × 3 hives, bounded random walks so charts read as plausible
  sensor data, not noise) that seeds its own Collector and Dashboard on
  first start — `docker compose --profile beekeeping up -d` alone takes
  a cold stack to a live, populated dashboard.
