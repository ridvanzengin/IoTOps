# Changelog

Dated, compressed history of what's actually shipped, across both this
repo and [custom-telegraf](https://github.com/ridvanzengin/custom-telegraf)
(IoTOps's sibling Go repo — entries below note when a change spans both).
For current status and what's still open, see
[docs/development-plan.md](docs/development-plan.md).

Newest first. Each entry is a compressed summary, not a full narrative —
where a bug fix taught something worth remembering (a real footgun, not
just "fixed a typo"), that's kept; blow-by-blow debugging steps aren't.

## 2026-07-22

**Fixed dashboard panels failing to load in production with "remaining
connection slots are reserved for roles with the SUPERUSER attribute."**
Root cause was a known, documented gap (see development-plan.md's
now-closed "No runaway-query timeout on interactive Panel queries" Known
Issue): `TelemetryRepository.execute_readonly` -- the query path behind
`DashboardService.run_panel_query`, i.e. actual panel-chart rendering, not
just the Panel Builder's SQL preview -- had no `asyncpg` timeout, unlike
every other query path (Query Rules' scheduled evaluation, the AI
Co-pilot's `query_telemetry` tool), which already enforce a 10s timeout.
As the demo's telemetry tables grew well past their size at initial
deployment, some panel queries got slow enough to hang, pinning one of
the production pool's deliberately tiny 5 connections indefinitely;
enough of those piling up exhausted the shared TimescaleDB instance's
connection cap entirely. Added the same 10s timeout convention to
`execute_readonly`/`TelemetryService.run_query`, with regression tests
mirroring the existing `execute_bounded`/`run_bounded_query` timeout
coverage.

## 2026-07-20

**Milestone 6 Slice 3 shipped: Co-pilot panel and dashboard suggestions,
plus session persistence (PR #25).** The Co-pilot can now propose either
a single new dashboard panel (`suggest_panel`) or a whole multi-panel
dashboard (`suggest_dashboard`) as a reviewable, prefilled draft — never
auto-created — grounded in real telemetry stats and existing
panel/dashboard/variable awareness (`list_existing_panels`). Panel
suggestions land in the existing Panel Builder prefill flow; dashboard
suggestions land in a new in-memory draft-dashboard state in the
Dashboard Editor (name + variables + panels, nothing persisted until an
explicit Save) — the one part of this slice with no existing form to
reuse. Both follow the always-available-tools lesson from Slice 2 from
the start (no intent-gating). Co-pilot conversations also now persist
across the panel being closed/reopened or the Events sidebar being shown
instead (moved into `EventsContext`'s `copilotSession`, previously reset
on unmount), with a "New session" control to start over deliberately.
This completes Milestone 6 (AI Assistant, v1.2) — all three Co-pilot
slices (Q&A, rule suggestions, panel/dashboard suggestions) are shipped.

**Gemini added as a free-tier alternative AI backend, switchable via
`AI_PROVIDER`.** `AiService`'s tool-calling loop and SQL generation now go
through a small `ChatProvider` interface (`app/ai/chat_provider.py`)
instead of the Anthropic SDK directly -- `AnthropicChatProvider` is a
pure passthrough (zero translation, zero regression risk); `GeminiChatProvider`
(`google-genai`) does the real work: translating our Anthropic-shaped tool
schemas/message history into Gemini's `Content`/`Part`/`FunctionCall`
structures and back. Two real bugs found live-testing it against the real
API (neither catchable by mocked tests alone): (1) "thinking" Gemini
models sign every function-call with an opaque `thought_signature` and
reject a later turn that replays the call without it -- a direct 400
`INVALID_ARGUMENT` repro'd and fixed by carrying the signature through
`ToolUseBlock`. (2) Gemini sometimes wraps a substituted variable token in
its own quotes (`WHERE machine_id = '$machine_id'`) despite prompt
guidance saying not to -- since the substituted value is already a quoted
string literal, this double-quoted into `''press-03''`, a syntax error
with no hint that quoting was the problem. Fixed structurally in
`substitute_macros` (strips a redundant quote pair around the token before
substituting) rather than relying on prompt compliance, since it's now
proven inconsistent across two different model providers.

**The public demo's AI routes no longer block outright** (`POST
/api/ai/sql`, `/query-rule-sql`, `/copilot` used to hard-403 whenever
`DEMO=true`, back when AI needed a paid Anthropic key public traffic
could burn through). Now that the default backend is free, they run for
real; `AiService` gained a `demo` flag so a genuine provider failure
(free-tier rate limit, most likely) shows a friendly "AI features in this
demo are temporarily limited" message instead of a raw error. The
suggest_*/query_*/list_existing_* tools were already provably read-only
or in-memory-only (never call a repository's create/update/delete) --
actually persisting anything still goes through the same
`POST /api/dashboard`/`/api/automater/rules`/etc. routes, which remain
gated.

**SQL-generation prompts didn't know how to write "latest reading per
entity" queries** -- live-tested via `/api/ai/sql`: a "latest weight per
hive" request generated `GROUP BY hive_id HAVING time = MAX(time)`,
invalid SQL (a non-aggregated column in HAVING) that Postgres rejects.
Added explicit `DISTINCT ON` guidance to both `build_sql_prompt` and
`build_query_rule_sql_prompt`, naming the invalid pattern directly so the
model recognizes and avoids it.

**Ollama retired -- every AI feature now runs on the same Anthropic
client.** SQL generation (`POST /api/ai/sql`, `POST /api/ai/query-rule-sql`,
backing the Panel Builder and Query Rule editor's NL-to-SQL boxes) used to
be a separate local-Ollama HTTP passthrough, kept apart from the
Anthropic-backed Co-pilot chat since Milestone 3. Switched
`AiService._generate_sql_from_prompt` onto `anthropic_client.messages.create`
directly; removed the Ollama HTTP client, `OLLAMA_BASE_URL`/`OLLAMA_MODEL`
config, and all related wiring from `dependencies.py`/`config.py`. One AI
backend, one API key, going forward.

**Root cause found for the Co-pilot's recurring "iteration budget
exhausted" and "dashboard has fewer panels than it should" bugs, chased
across several rounds of prompt-wording changes: `max_tokens=500` on the
Anthropic call, truncating `suggest_dashboard`'s larger tool-call payloads
(a 4-6 panel dashboard's JSON, each panel with a full SQL string, easily
exceeds that).** Added per-iteration tool-call logging (there was no
`logging.basicConfig` anywhere in the app before this, so nothing
surfaced) and reproduced live: 17 of 19 `suggest_dashboard` calls in one
real turn had `name`/`description`/`variables` but no `panels` key at all
-- the model ran out of tokens before reaching that field, the tool
correctly rejected the incomplete call, and the model just retried the
same truncated shape until the budget ran out. Fixed by bumping to
`max_tokens=4096`. Same truncation also explained a live
`[[quick-replies]]` block leaking raw markup into the chat when it got
cut off before its closing tag -- hardened `_extract_quick_replies` to
strip an unterminated block instead of leaving it visible either way.

**`DashboardSuggestionState` now structurally enforces two more
invariants**, after live testing showed prompt-only guidance wasn't
reliably followed: at least 3 panels (was 2; guidance targets 4+), and
every declared variable must actually be filtered or grouped by at least
one panel (chain parents excepted, since narrowing a child variable's own
options is real work even without a direct SQL reference) -- a variable
declared "for later" with no panel using it now gets rejected instead of
shipping as dead UI. Guidance also hardened against grouping by
infrastructure columns that merely look like real entities (e.g. `host`
holding Docker container ids, narrated as "4 systems" without ever
checking the actual distinct values) and against high-cardinality
group-by producing an unreadable many-line panel.

## 2026-07-18

**`AutomaterEditor.tsx`'s "Create Rule" button disabled with no explanation
when an Automater isn't picked yet.** Following up on the AI rule-drafting
work: a Co-pilot-suggested rule prefills table/conditions/message/severity
but deliberately leaves `automaterId` unset (which deployment should host
the rule isn't inferable from data -- see yesterday's entries). Landing on
a form that already looks complete, with no visible reason the submit
button was greyed out, was confusing. Worse, the tag-keys warning that
*was* showing in that state was actively misleading: `missingTagKeys`
compared referenced identifiers against `inputTagKeys`, which defaults to
`[]` before an Automater/Collector resolves a real input -- so it
flagged every referenced identifier as "not in the reused input's Tag
Keys" even though nothing had been reused yet, there was simply no input
to check against. Fixed both: `missingTagKeys` now returns empty until
`derivedInput` actually resolves, and a plain hint appears next to the
Automater field itself when it's still unset, explaining why the button
is disabled and what to do about it. Query Rules have no equivalent gap --
`QueryRuleEditor.tsx` has no Automater field at all; scheduled queries run
standalone against TimescaleDB, not through an Automater's Telegraf
process.

## 2026-07-17

**Co-pilot Slice 2 — Rule Suggestions shipped.** "Suggest an automation" on
`/automaters` and `/query-rules` opens the Co-pilot with a
`suggest-automation` intent. Two new tools -- `list_existing_rules`
(avoids proposing a duplicate, reuses existing identifier naming) and
`suggest_automation` (the actual proposal, captured structurally like
`flag_missing_context` rather than executed) -- join the existing
`query_telemetry` tool, which the model now also uses to ground a
threshold in real min/max/avg/percentile stats before proposing one. The
model decides between a real-time Automater Rule and a scheduled Query
Rule based on whether the request needs a single-table condition or a
cross-table/time-windowed aggregate. `CopilotAnswerResponse` gains a
`suggestion` field, rendered by `CopilotChat.tsx` as a card that deep-links
into `/automaters/new` or `/query-rules/new` prefilled via React Router
`state` -- never auto-created. Refinement ("use the average instead") is
just continued conversation, grounded by a machine-readable recap appended
to the stored assistant message (see `_SUGGESTION_CONTEXT_START`/`_END` in
`app/ai/service.py`).

Verified live against two real demo projects (Manufacturing Line,
Beekeeping) using the real Anthropic API, not just the 77 mocked backend
tests -- surfaced a real bug mocks alone couldn't: on a refinement turn,
the model sometimes echoes the `[[suggestion-context]]...` recap marker
itself (mimicking what it saw in its own prior turn's history), producing
two blocks in one answer. The frontend's strip regex wasn't global, so
only the first got removed and the second leaked raw JSON into the chat
bubble -- fixed by making the strip global, which holds regardless of how
many blocks appear, not just this specific cause.

**Same-day follow-up, from a real user session detecting hornet attacks on
hives:** `MAX_COPILOT_ITERATIONS` bumped 6 → 10 -- a genuinely
cross-table request (weight-loss + elevated-sound combined) needed more
tool-call round-trips than the cap allowed and hit a hard "couldn't finish
within the allotted steps" error mid-conversation; the suggest-automation
system prompt addendum also now tells the model to batch multiple
columns' stats into one `query_telemetry` call instead of one per column,
to spend the budget it does have more efficiently. Added a general
quick-replies mechanism (`[[quick-replies]]` block instructions in the
base system prompt, parsed server-side into `CopilotAnswerResponse
.quick_replies`, rendered as clickable chips in `CopilotChat.tsx`) so a
"pick between these options" answer is tappable instead of prose the user
had to retype ("option b") back at the model. The Co-pilot's greeting and
post-project-pick line are now intent-aware for the suggest-automation
flow ("Which project would you like to set up an automation for?" instead
of the generic Q&A greeting), and the old "or say 'surprise me'" text
instruction became an actual clickable chip ("Analyze my telemetry and
suggest an automation"), reusing the same chip mechanism as project
selection and quick-replies rather than a third UI pattern.

**Second same-day follow-up, from a real hive-theft-detection session (8
distinct issues, all fixed):**
- **Cross-project schema leak (the significant one).** The Co-pilot's
  system prompt was built from `TelemetryService.get_schema()`'s *global*
  table list -- TimescaleDB has no per-project table isolation, a
  "project" is a Mongo-side grouping of Collectors, so every project's
  Co-pilot saw every other project's tables too. Live symptom: opening the
  Co-pilot from the Beekeeping project and asking about theft got a reply
  about vehicle/equipment theft, because vehicle tables were sitting right
  there in its context. Fixed with `AiService._project_schema`, which
  derives "tables this project's own Collectors actually write to" the
  same way `AutomaterEditor.tsx`'s DB Schema panel already does
  client-side, and scopes the schema block to just those.
- **SQL validator rejected legitimate CTEs.** `validate_select_only_sql`
  only accepted a literal `^SELECT` prefix, so an AI-suggested Query Rule
  using a `WITH ... AS (...) SELECT ...` CTE (needed for a window-function
  weight-change comparison) failed with "Only single, read-only SELECT
  statements are allowed" the moment the user tried to run it. Fixed by
  also accepting a `WITH` prefix -- but that reopens a real hole (Postgres
  only allows INSERT/UPDATE/DELETE as a *named CTE*, never as a plain
  FROM-subquery, so rejecting WITH outright had accidentally made a
  data-modifying CTE structurally impossible); closed it with an explicit
  keyword blocklist instead. Shared by every SQL entry point (Panel
  Builder, Query Rules, the Co-pilot's own `query_telemetry`), not just
  this one.
- Numbered options and confirmation-style questions ("does this threshold
  look right?") weren't reliably getting a `[[quick-replies]]` block --
  the original instruction's "discrete choices" framing apparently didn't
  read as covering a plain confirmation. Made the trigger condition
  explicit and closer to exhaustive.
- The model reliably used `**bold**` and numbered lists despite an
  explicit "no markdown of any kind" instruction. Stopped fighting it:
  the prompt now allows both, and `CopilotChat.tsx` actually renders
  `**bold**` (a small hand-rolled inline parser, not a new dependency)
  instead of showing literal asterisks.
- Added an instruction to sanity-check values against real-world domain
  knowledge before restating them as fact -- the model had said "hives
  typically weigh 30-2830 kg" (a real hive weighs tens of kilograms, not
  thousands) as if that were normal.
- The seed "surprise me" chip and confirmed-working quick-reply chips
  were re-verified live to render as actual chips, not a message bubble.

**Third same-day follow-up: a full 8-angle code review of the whole
feature (correctness, reuse, simplification, efficiency, altitude,
CLAUDE.md conventions) before committing, verified against the running
backend, surfaced 6 more real issues, all fixed:**
- The keyword blocklist added for the CTE fix above scanned the *whole*
  SQL string, including quoted data -- `WHERE action = 'delete'` was
  rejected for containing the word "delete" as a value, not a statement.
  Now blanks out string literals before scanning.
- Allowing `WITH` also allowed `WITH RECURSIVE` -- an unbounded recursive
  CTE run through the Panel Builder's ad hoc SQL path (which has no query
  timeout, unlike the Co-pilot's own bounded `query_telemetry`) is a real
  resource-exhaustion risk. `RECURSIVE` added to the blocklist.
- `AutomaterEditor.tsx`/`QueryRuleEditor.tsx`'s suggestion-prefill effects
  only ran on mount, but the Co-pilot chat panel is mounted once at the
  app-shell level and outlives route navigation -- refining a suggestion
  and clicking "Open in builder" a second time while already on that
  route silently kept the first draft's stale values. Now depends on
  `location.state` instead of running once.
- `frontend/src/types/ai.ts` hand-copied `RuleSeverity`/`ResolveMode`/
  `ConditionOperator`/`QueryRuleSchedule` instead of importing the
  existing ones from `types/automater.ts`/`types/queryRule.ts` -- real
  duplication risk if those ever changed without this file following.
  Now imports them (and reuses `ConditionPayload` directly instead of a
  redundant `ConditionSuggestion`).
- `_extract_quick_replies` only stripped the *first* `[[quick-replies]]`
  block, the same non-global mistake already found and fixed for the
  sibling `[[suggestion-context]]` marker earlier today. Now strips every
  occurrence (using the *last* block's labels, since the prompt places
  the real one at the end of the answer) and the frontend gained a
  matching backstop regex, mirroring the suggestion-context treatment.
- If the model's entire final answer was just a `[[quick-replies]]` block
  with no prose, extraction left an empty string, which raised a hard
  error and silently discarded a suggestion already built earlier in the
  same turn. Now falls back to a plain line instead of failing when a
  suggestion exists.

Prioritized by portfolio-project relevance (does a visitor ever see it,
does it make the demo look broken, is it cheap to fix) over
production-scale concerns -- deliberately left unfixed: an unguarded
plugin-registry lookup that would only break if a Collector's plugin type
is later renamed/removed (low odds, clean 404 if it ever happens), a
latent `\n\n`-prefix gap in the suggestion-context strip regex with no
observed trigger, and two efficiency findings (redundant service
construction in `get_ai_service()`, a full schema+collector refetch per
Co-pilot turn) that are invisible at demo scale.

**Fourth same-day follow-up: `suggest_automation`/`list_existing_rules`
are no longer gated behind an `intent` flag -- they're available in every
Co-pilot conversation now.** A real session opened the plain Co-pilot
(the generic icon, not the dedicated "Suggest an automation" button on
`/automaters`/`/query-rules`) and typed "I want to create a rule." Five
rounds of increasingly detailed clarifying questions later -- including a
real telemetry check -- the model said "I don't have the ability to
create or modify rules directly," because it genuinely didn't: the
suggestion tools were only ever attached to the tool list when
`intent="suggest-automation"`, which only that one button ever set.

Rather than making the dead end fail faster, removed the gate entirely:
`COPILOT_TOOLS` (`app/ai/tools.py`) is now always the full five-tool set,
`build_copilot_system_prompt` always includes the rule-creation guidance
(reworded to trigger off the model recognizing intent from the user's own
words -- "I want to create a rule," "alert me when..." -- rather than an
externally-set flag), and `CopilotQuestionRequest.intent` /
`answer_copilot_question`'s `intent` param are gone from the backend
entirely. `intent` still exists as a `CopilotChat.tsx` prop -- opening via
the dedicated button still shows an intent-aware greeting and a seed
suggestion chip -- but it's now purely local UI framing, never sent to the
server; the model's own judgment (already relied on to pick between the
other tools correctly) keeps `suggest_automation` from firing on an
unrelated question, the same way `flag_missing_context` already does.

Also addressed directly: the same session's answers were long, multi-
paragraph walls of text bundling 3-4 questions into one turn before ever
proposing anything. Added an explicit brevity instruction (a few sentences
per turn, one or two questions at most) and a "propose a fast, adjustable
draft with reasonable defaults instead of interrogating for every
parameter first" instruction -- refinement afterward is cheap (that's what
quick-replies are for), so front-loading every possible question isn't
necessary.

Re-verified live, replaying the reported scenario from the plain Co-pilot
icon: "I want to create a rule" → "detect co2 anomalies, spikes
specifically" → one grounded threshold question with quick-reply chips →
a working suggestion card, in 3 short turns instead of 6 long ones ending
in refusal.

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

**AI Co-pilot, slice 1: read-only Event/Occurrence + telemetry Q&A.** The
activity bar's reserved Co-pilot panel slot (placeholder since Milestone
5) now has a real chat component. Deliberately a different model backend
from the rest of `app/ai/`: this endpoint uses the user's own Anthropic
API key (`claude-haiku-4-5`) rather than the local Ollama model, both to
keep cost trivial ($1/$5 per MTok) and to demonstrate real Claude API
usage — existing SQL generation (`/api/ai/sql`, `/api/ai/query-rule-sql`)
is untouched, still Ollama-backed.

Architecture is real tool-calling, not context-stuffing: a manual
4-iteration loop (`AiService.answer_copilot_question`) gives the model two
tools it calls on demand — `query_occurrences` (structured Event lookup,
`project_id` bound server-side, never model-facing) and `query_telemetry`
(model-written read-only SQL, reusing the existing
`validate_select_only_sql` guardrail plus a new row cap + 10s timeout via
`TelemetryService.run_bounded_query`). The timeout addresses, for this one
call site, the "no runaway-query timeout on interactive Panel queries" gap
already tracked in Known Issues below. Unlike the original context-
stuffing design (which could only answer questions from a fixed pre-
fetched occurrence window), real tool-calling lets the model ask for
exactly the data it needs, including actual telemetry *values* — verified
live: "what was the average temperature for hive-3" returned 34.49°C,
matching a direct `AVG(temperature)` query against TimescaleDB exactly.

Verified end-to-end against live demo data, not just unit tests: occurrence
counts/timestamps cross-checked against direct DB queries, a multi-turn
follow-up ("and how does that compare to hive-4?") correctly resolved
against client-resent history, and an attempt to coax a destructive query
("delete the old readings") was correctly declined — the model reasoned
from its own tool descriptions that it had no delete capability, without
needing the SQL guardrail to catch it. Measured cost: ~$0.008/question
(6.5K input + ~300 output tokens for a 2-tool-call question) — comfortably
inside the project's $5 budget for hundreds of questions.

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
