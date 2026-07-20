from datetime import datetime, timezone
from uuid import uuid4

from app.ai.models import AiVariableHint
from app.ai.prompts import build_copilot_system_prompt, build_query_rule_sql_prompt, build_sql_prompt
from app.telemetry.models import TelemetryColumn, TelemetryTableSchema


def _schema() -> list[TelemetryTableSchema]:
    return [
        TelemetryTableSchema(
            table="device_metrics",
            columns=[
                TelemetryColumn(name="time", data_type="timestamp with time zone", is_nullable=False),
                TelemetryColumn(name="temperature", data_type="double precision", is_nullable=True),
            ],
        )
    ]


def test_prompt_includes_schema_and_request() -> None:
    prompt = build_sql_prompt("show temperature for the last hour", _schema())

    assert "device_metrics(time timestamp with time zone, temperature double precision)" in prompt
    assert "Request: show temperature for the last hour" in prompt


def test_prompt_instructs_time_range_macros_over_hardcoded_intervals() -> None:
    prompt = build_sql_prompt("show temperature for the last 15 minutes", _schema())

    assert "$__timeFrom" in prompt
    assert "$__timeTo" in prompt
    assert "NOW() - INTERVAL" in prompt


def test_prompt_instructs_no_aggregation_unless_requested() -> None:
    prompt = build_sql_prompt("show temperature", _schema())

    assert "Do not aggregate" in prompt


def test_prompt_instructs_ordering_and_timestamp_column() -> None:
    prompt = build_sql_prompt("show temperature", _schema())

    assert "ORDER BY" in prompt
    assert "timestamp column" in prompt


def test_prompt_includes_variable_hints_when_provided() -> None:
    prompt = build_sql_prompt(
        "show temperature for the selected hive",
        _schema(),
        variables=[AiVariableHint(name="hive_id", label="Hive")],
    )

    assert "$hive_id" in prompt
    assert "Hive" in prompt


def test_prompt_omits_variable_section_when_none_provided() -> None:
    prompt = build_sql_prompt("show temperature", _schema())

    assert "dashboard defines the following variables" not in prompt


def test_prompt_instructs_distinct_on_for_latest_per_entity_requests() -> None:
    # Regression: live-tested via /api/ai/sql -- a "latest weight per hive"
    # style request generated `SELECT hive_id, weight_kg FROM hive_weight
    # ... GROUP BY hive_id HAVING time = MAX(time)`, which Postgres rejects
    # ("column must appear in the GROUP BY clause or be used in an
    # aggregate function") since weight_kg is neither aggregated nor
    # grouped, and HAVING time = MAX(time) doesn't fix that. DISTINCT ON
    # is the correct, valid pattern for "one row per entity, newest first".
    prompt = build_sql_prompt("show the latest weight per hive", _schema())

    assert "DISTINCT ON" in prompt
    assert "HAVING time = MAX(time)" in prompt  # named explicitly as the invalid pattern to avoid


def test_query_rule_prompt_includes_schema_and_request() -> None:
    prompt = build_query_rule_sql_prompt("stations with sustained high wind", _schema())

    assert "device_metrics(time timestamp with time zone, temperature double precision)" in prompt
    assert "Request: stations with sustained high wind" in prompt


def test_query_rule_prompt_instructs_hardcoded_relative_windows_not_macros() -> None:
    # The opposite instruction of build_sql_prompt's -- there's no
    # dashboard time range to substitute from here, so the prompt
    # explicitly forbids the macros it tells Panel queries to use instead.
    prompt = build_query_rule_sql_prompt("average over the last hour", _schema())

    assert "Do NOT use" in prompt
    assert "$__timeFrom" in prompt
    assert "now() - interval" in prompt


def test_query_rule_prompt_instructs_one_row_per_matching_entity() -> None:
    prompt = build_query_rule_sql_prompt("show temperature", _schema())

    assert "GROUP BY" in prompt
    assert "HAVING" in prompt


def test_query_rule_prompt_instructs_distinct_on_for_latest_reading_requests() -> None:
    # Companion to build_sql_prompt's own regression (see
    # test_prompt_instructs_distinct_on_for_latest_per_entity_requests) --
    # a Query Rule asking about each entity's LATEST reading specifically
    # is exactly the request shape rule 2's own "GROUP BY entity, HAVING
    # aggregate" pattern doesn't cover (time isn't an aggregate), so it
    # needs its own explicit DISTINCT-ON-subquery guidance too.
    prompt = build_query_rule_sql_prompt("alert if the most recent temperature is above 90", _schema())

    assert "DISTINCT ON" in prompt
    assert "HAVING time = MAX(time)" in prompt


def test_query_rule_prompt_encourages_cross_table_conditions() -> None:
    prompt = build_query_rule_sql_prompt("show temperature", _schema())

    assert "Cross-table conditions are expected" in prompt


def test_query_rule_prompt_does_not_require_ordering() -> None:
    prompt = build_query_rule_sql_prompt("show temperature", _schema())

    assert "No ORDER BY is needed" in prompt


def test_query_rule_prompt_forbids_clarifying_questions() -> None:
    prompt = build_query_rule_sql_prompt("average humidity is higher than 60 in last 15 minutes", _schema())

    assert "never ask a clarifying question" in prompt


def test_query_rule_prompt_includes_identifiers_hint_when_provided() -> None:
    prompt = build_query_rule_sql_prompt("average humidity per hive", _schema(), identifiers=["hive_id"])

    assert "hive_id" in prompt
    assert "author's own chosen" in prompt


def test_query_rule_prompt_omits_identifiers_section_when_none_provided() -> None:
    prompt = build_query_rule_sql_prompt("show temperature", _schema())

    assert "author's own chosen" not in prompt


def test_query_rule_prompt_repeats_identifiers_hint_near_the_request() -> None:
    # Live-tested: a single schema-adjacent mention wasn't reliably
    # followed for a fully generic request with no textual hint of the
    # entity -- repeating it right before "Request:" measurably fixed
    # that. See build_query_rule_sql_prompt's own comment.
    prompt = build_query_rule_sql_prompt("average humidity is higher than 60", _schema(), identifiers=["hive_id"])

    assert prompt.count("hive_id") >= 2
    request_index = prompt.rindex("Request:")
    assert "hive_id" in prompt[:request_index]


def test_copilot_system_prompt_includes_schema_and_current_time() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "device_metrics(time timestamp with time zone, temperature double precision)" in prompt
    assert now.isoformat() in prompt


def test_copilot_system_prompt_mentions_all_tools() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "query_occurrences" in prompt
    assert "query_telemetry" in prompt
    assert "flag_missing_context" in prompt


def test_copilot_system_prompt_includes_ai_context_when_provided() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(
        _schema(), now=now, ai_context="val1 is coolant temperature in Celsius"
    )

    assert "val1 is coolant temperature in Celsius" in prompt
    assert "trust it over guessing" in prompt


def test_copilot_system_prompt_omits_context_block_when_not_provided() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "trust it over guessing" not in prompt


def test_copilot_system_prompt_instructs_against_fabricating_answers() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "say so plainly" in prompt


def test_copilot_system_prompt_instructs_quick_replies_format() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "[[quick-replies]]" in prompt
    assert "[[/quick-replies]]" in prompt


def test_copilot_system_prompt_requires_quick_replies_for_confirmation_questions() -> None:
    # Regression: a live session showed the model asking confirmation-
    # style questions ("does this approach make sense?") without a
    # quick-replies block -- the original instruction only mentioned
    # "discrete choices", which the model apparently didn't read as
    # covering a yes/no confirmation. Made explicit.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "confirm a proposed approach" in prompt
    assert "yes/no-shaped question" in prompt


def test_copilot_system_prompt_allows_bold_and_numbered_lists() -> None:
    # Regression: the model reliably uses **bold**/numbered lists to
    # enumerate options despite an earlier "no markdown of any kind"
    # instruction -- rather than keep fighting a strong model tendency,
    # the frontend now renders both, so the prompt should say so instead
    # of forbidding formatting it's actually going to receive raw.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "**bold**" in prompt
    assert "## headers" in prompt  # still disallowed


def test_copilot_system_prompt_instructs_sanity_checking_implausible_values() -> None:
    # Regression: the model stated "hives typically weigh 30-2830 kg" as
    # if that were a normal fact -- a real hive weighs tens of kilograms,
    # not thousands. It should flag an implausible magnitude rather than
    # repeat it uncritically.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "physically implausible" in prompt


def test_copilot_system_prompt_always_includes_suggestion_tools_and_guidance() -> None:
    # Regression: these used to be gated behind an `intent` flag only set
    # when the panel was opened via the dedicated "Suggest an automation"
    # button. A real session showed a plain "I want to create a rule"
    # typed into the ordinary Co-pilot getting a long conversation that
    # ended in "I don't have the ability to create rules" -- the tool
    # genuinely wasn't there. Every conversation gets the full tool set now.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "suggest_automation" in prompt
    assert "list_existing_rules" in prompt
    assert "automater_rule" in prompt
    assert "query_rule" in prompt
    assert "rule-creation request" in prompt


def test_copilot_system_prompt_instructs_proposing_a_fast_draft_over_interrogating() -> None:
    # Regression: a real session asked the user roughly 15 clarifying
    # questions across 5 rounds before ever proposing a draft. The prompt
    # should push toward a fast, adjustable first draft instead.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "Don't interrogate the user for every parameter" in prompt


def test_copilot_system_prompt_instructs_brevity() -> None:
    # Regression: the same real session's answers were long, multi-
    # paragraph walls of text with several questions bundled into one turn.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "Be brief" in prompt


def test_copilot_system_prompt_always_includes_panel_suggestion_tools_and_guidance() -> None:
    # Same always-on principle as suggest_automation/list_existing_rules
    # -- see the "Lesson learned" note in docs/development-plan.md --
    # applied to the panel-suggestion tools from the start.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "suggest_panel" in prompt
    assert "list_existing_panels" in prompt
    assert "panel-suggestion request" in prompt


def test_copilot_system_prompt_omits_dashboard_block_when_not_provided() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "currently viewing dashboard" not in prompt


def test_copilot_system_prompt_always_includes_dashboard_suggestion_tool_and_guidance() -> None:
    # Same always-on principle as every other suggestion tool.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "suggest_dashboard" in prompt
    assert "dashboard-suggestion request" in prompt


def test_copilot_system_prompt_dashboard_guidance_instructs_proposing_every_panel() -> None:
    # The one thing genuinely different from a single panel suggestion --
    # propose the whole starter set, not just the strongest idea.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "EVERY panel worth having" in prompt


def test_copilot_system_prompt_dashboard_guidance_targets_at_least_four_panels() -> None:
    # User feedback: a 2-panel AI-generated dashboard felt thin compared
    # to a 4-panel one from another session -- the tool's hard floor of 3
    # is a rejection threshold, not a target; guidance should push the
    # model to not just barely clear it.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "aim for at least 4 panels" in prompt
    assert "the tool rejects fewer than 3" in prompt


def test_copilot_system_prompt_dashboard_guidance_forbids_asking_to_add_already_identified_panels() -> None:
    # Regression: a live session surveyed the data, named 4 candidate
    # panels in prose, but only included 2 in the suggest_dashboard call
    # and asked "would you like me to add [the other two] before you
    # create it?" with quick-replies -- an incomplete first draft (and a
    # declared Array variable that neither included panel actually used)
    # for no real benefit over just including everything up front.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "do NOT propose a smaller subset" in prompt
    assert "never as a way to defer including panels you've already decided are worth having" in prompt


def test_copilot_system_prompt_dashboard_guidance_forbids_declaring_an_unused_variable() -> None:
    # Regression: a live session declared a "Panel Array" variable, but
    # all 4 proposed panels were flat fleet-wide overviews that never
    # actually filtered or grouped by it -- a purely decorative variable
    # that reads as broken to the user, not helpful. An earlier version of
    # this guidance explicitly permitted this ("declared-but-unused is
    # fine, for later") -- live testing showed that's not what users want;
    # a declared variable must be exercised by at least one panel in the
    # same call, or not declared at all.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "a declared variable is NOT allowed to sit unused" in prompt
    assert "EARN that variable by including at least one panel" in prompt


def test_copilot_system_prompt_dashboard_guidance_requires_declaring_a_used_grouping_column() -> None:
    # Regression: a live session had the model GROUP BY a genuinely
    # meaningful entity column (panel_array_id, real values like
    # 'array-1') in one of its own proposed panels, yet still declared no
    # variables at all -- an inconsistency the guidance now forbids
    # outright, not just discourages.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "you MUST declare that column as a variable" in prompt


def test_copilot_system_prompt_dashboard_guidance_allows_mixing_overview_and_filtered_panels() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "a single dashboard can mix both" in prompt


def test_copilot_system_prompt_dashboard_guidance_prefers_filtering_over_high_cardinality_groupby() -> None:
    # User feedback: real deployments have many instances of a per-entity
    # column (many device_ids, hives, machines) -- a panel that groups/
    # series_by's that column to draw one line per entity is unreadable at
    # that scale. The default should lean toward a variable-filtered (one
    # entity at a time) or aggregated panel, not a flat many-line overview.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "lean toward filtered-by-variable as the default" in prompt
    assert "unreadable, overlapping mess" in prompt


def test_copilot_system_prompt_dashboard_guidance_requires_variable_sql_agreement() -> None:
    # Regression: the model described "a Machine filter variable" in
    # prose and wrote panel sql referencing $machine_id, but the actual
    # variables list was empty -- every panel silently returned no data.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "these two must always agree" in prompt.lower()


def test_copilot_system_prompt_dashboard_guidance_forbids_giving_up_to_prose_after_an_error() -> None:
    # Regression: a live session had suggest_dashboard fail once (called
    # with an empty panels list), and instead of fixing the input and
    # retrying, the model apologized and described the whole dashboard in
    # prose instead -- no card, nothing for the user to act on.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "Do not respond to a suggest_dashboard error by apologizing" in prompt


def test_copilot_system_prompt_includes_dashboard_hint_when_provided() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
    dashboard_id = uuid4()

    prompt = build_copilot_system_prompt(
        _schema(),
        now=now,
        dashboard_hint=(dashboard_id, "Apiary Overview", [AiVariableHint(name="hive_id", label="Hive")]),
    )

    assert "Apiary Overview" in prompt
    assert str(dashboard_id) in prompt
    assert "$hive_id" in prompt


def test_copilot_system_prompt_panel_guidance_forbids_narrating_without_calling_suggest_panel() -> None:
    # Regression: a live session had the model describe a specific panel
    # ("I'll create an Environmental Summary panel...") and ask "does this
    # look right?" with quick-replies, but never actually called
    # suggest_panel -- no suggestion card, nothing to open. The narration
    # sounded final enough that the user reasonably expected a card.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "Never describe a specific proposed panel in prose" in prompt
    assert "leaves the user with nothing to open" in prompt


def test_copilot_system_prompt_panel_guidance_requires_checking_distinct_values_before_grouping() -> None:
    # Regression: a live session grouped by "host" and narrated it in
    # prose as "4 inverter systems", but the actual distinct values were
    # Docker container id hex strings -- a genuine hallucination, since a
    # column's name alone ("host") was treated as evidence it's a real
    # business entity without ever checking what the values looked like.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "check its actual DISTINCT" in prompt
    assert "container ids" in prompt
    assert "hashes, hex strings" in prompt


def test_copilot_system_prompt_panel_guidance_warns_against_high_cardinality_groupby() -> None:
    # Companion to the distinct-values check above: even a genuinely real
    # entity column (not a hallucination) shouldn't be grouped/series_by'd
    # directly once it has many instances -- stacking many lines/bars in
    # one panel is unreadable regardless of whether the entity is real.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "check the COUNT of distinct values" in prompt
    assert "unreadable, overlapping mess" in prompt


def test_copilot_system_prompt_panel_guidance_forbids_generic_menu_for_vague_requests() -> None:
    # Regression: a plain "I want to add a panel to dashboard" got a
    # static menu of generic categories ("a metric not yet displayed? a
    # comparison? a summary?") instead of the model actually looking at
    # the data first, unlike an explicit "look at my telemetry" request
    # which did produce a real, data-grounded analysis.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "do NOT open with a generic menu of question categories" in prompt
    assert "here's what stands out" in prompt


def test_copilot_system_prompt_panel_guidance_requires_refreshing_existing_panels_check() -> None:
    # Regression: a long conversation called list_existing_panels once
    # early on, then much later proposed a panel that duplicated one the
    # user had since saved (via a separate conversation) -- the model
    # never re-checked before finalizing.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "Re-call it right before you call suggest_panel" in prompt


def test_copilot_system_prompt_panel_guidance_forbids_scope_qualifiers_in_titles() -> None:
    # Regression: a live session titled a variable-filtered panel
    # "Vibration Over Time (Selected Machine)" -- the dashboard's own
    # variable selector already shows what's selected, so the qualifier
    # is redundant noise, worse once repeated across several panels.
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "Vibration Over Time (Selected Machine)" in prompt
    assert "naming convention" in prompt.lower()


def test_copilot_system_prompt_dashboard_hint_without_variables_omits_variable_block() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
    dashboard_id = uuid4()

    prompt = build_copilot_system_prompt(
        _schema(), now=now, dashboard_hint=(dashboard_id, "Apiary Overview", [])
    )

    assert "Apiary Overview" in prompt
    assert "defines the following variables" not in prompt
