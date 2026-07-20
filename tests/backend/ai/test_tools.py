from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from mongomock_motor import AsyncMongoMockClient

from app.ai.tools import (
    SUGGEST_PANEL_TOOL,
    run_flag_missing_context,
    run_list_existing_panels,
    run_list_existing_rules,
    run_query_occurrences,
    run_query_telemetry,
    run_suggest_automation,
    run_suggest_dashboard,
    run_suggest_panel,
)
from app.automater.models import Automater, Condition, Rule
from app.dashboard.models import Dashboard, LineChart, Panel, PanelPosition, Query, Variable
from app.event.models import Event, EventFlag, OccurrenceStatus
from app.event.repository import EventRepository, to_document
from app.event.service import EventService
from app.query_rule.models import QueryRule, QueryRuleSchedule
from app.shared.models import InputPlugin, OutputPlugin
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.ai.fakes import FakeAutomaterService, FakeDashboardService, FakeQueryRuleService
from tests.backend.telemetry.fakes import FakePool


async def _event_service_with(*events: Event) -> EventService:
    database = AsyncMongoMockClient()["iotops"]
    for event in events:
        await database["events"].insert_one(to_document(event))
    return EventService(
        repository=EventRepository(database, pubsub_redis_client=AsyncMock(), firing_redis_client=AsyncMock())
    )


def _event(project_id, rule_name: str = "swarm-alert", **overrides) -> Event:
    defaults: dict = {
        "project_id": project_id,
        "automater_id": uuid4(),
        "rule_id": uuid4(),
        "rule_name": rule_name,
        "table": "hive_metrics",
        "flag": EventFlag.MATCH,
        "matched_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Event(**defaults)


async def test_query_occurrences_filters_by_rule_name() -> None:
    project_id = uuid4()
    service = await _event_service_with(
        _event(project_id, rule_name="swarm-alert"),
        _event(project_id, rule_name="low-battery"),
    )

    result = await run_query_occurrences(service, project_id, {"rule_name": "swarm"})

    assert "swarm-alert" in result
    assert "low-battery" not in result


async def test_query_occurrences_filters_by_since_hours() -> None:
    project_id = uuid4()
    service = await _event_service_with(
        _event(project_id, matched_at=datetime.now(timezone.utc) - timedelta(hours=48)),
    )

    result = await run_query_occurrences(service, project_id, {"since_hours": 1})

    assert "No occurrences found" in result


async def test_query_occurrences_caps_limit_at_max() -> None:
    project_id = uuid4()
    service = await _event_service_with(*[_event(project_id) for _ in range(3)])

    # Should not raise despite requesting far more than the cap -- just
    # silently clamps, same as the API's own limit handling elsewhere.
    result = await run_query_occurrences(service, project_id, {"limit": 10_000})

    assert "swarm-alert" in result


async def test_query_occurrences_rejects_invalid_status() -> None:
    project_id = uuid4()
    service = await _event_service_with(_event(project_id))

    result = await run_query_occurrences(service, project_id, {"status": "BOGUS"})

    assert "Invalid status" in result


async def test_query_occurrences_filters_by_valid_status() -> None:
    project_id = uuid4()
    service = await _event_service_with(_event(project_id))

    result = await run_query_occurrences(project_id=project_id, event_service=service, input_={"status": "ACTIVE"})

    assert "swarm-alert" in result
    assert OccurrenceStatus.ACTIVE.value in result


def _telemetry_service(**kwargs) -> TelemetryService:
    pool = FakePool(tables=["device_metrics"], **kwargs)
    return TelemetryService(repository=TelemetryRepository(pool))


async def test_query_telemetry_rejects_non_select_sql() -> None:
    service = _telemetry_service()

    result = await run_query_telemetry(service, {"sql": "DELETE FROM device_metrics"})

    assert "Query rejected" in result


async def test_query_telemetry_returns_formatted_rows() -> None:
    sql = "SELECT temperature FROM device_metrics"
    service = _telemetry_service(query_results={sql: [{"temperature": 21.5}, {"temperature": 22.0}]})

    result = await run_query_telemetry(service, {"sql": sql})

    assert "temperature" in result
    assert "21.5" in result
    assert "22.0" in result


async def test_query_telemetry_reports_no_rows() -> None:
    sql = "SELECT temperature FROM device_metrics WHERE 1=0"
    service = _telemetry_service(query_results={sql: []})

    result = await run_query_telemetry(service, {"sql": sql})

    assert "no rows" in result


async def test_query_telemetry_reports_database_errors() -> None:
    sql = "SELECT bogus_column FROM device_metrics"
    service = _telemetry_service(query_errors={sql: "column does not exist"})

    result = await run_query_telemetry(service, {"sql": sql})

    assert "Query failed" in result


async def test_query_telemetry_reports_timeout() -> None:
    sql = "SELECT * FROM device_metrics"
    service = _telemetry_service(query_timeouts={sql})

    result = await run_query_telemetry(service, {"sql": sql})

    assert "Query failed" in result


def test_flag_missing_context_returns_an_ack() -> None:
    # Purely a structural signal (see AiService.answer_copilot_question,
    # which reads the tool_use's own input, not this return value) -- the
    # model still needs a tool_result to continue the loop.
    result = run_flag_missing_context({"column": "val1", "reason": "no unit given"})

    assert isinstance(result, str)
    assert result


def _automater(project_id, rules: list[Rule]) -> Automater:
    return Automater(
        project_id=project_id,
        name="Test Automater",
        inputs=[InputPlugin(plugin_type="mqtt_consumer", name="in")],
        outputs=[OutputPlugin(plugin_type="celery", name="out")],
        rules=rules,
    )


def _rule(**overrides) -> Rule:
    defaults: dict = {
        "name": "High temperature",
        "table": "device_metrics",
        "conditions": [Condition(column="temperature", operator=">", value=90)],
        "identifiers": ["device_id"],
    }
    defaults.update(overrides)
    return Rule(**defaults)


def _query_rule(project_id, **overrides) -> QueryRule:
    defaults: dict = {
        "project_id": project_id,
        "name": "High average vibration",
        "sql": "SELECT machine_id FROM machine_metrics GROUP BY machine_id HAVING AVG(vibration) > 5",
        "identifiers": ["machine_id"],
        "schedule": QueryRuleSchedule(interval="15m"),
    }
    defaults.update(overrides)
    return QueryRule(**defaults)


async def test_list_existing_rules_reports_none_when_project_has_no_rules() -> None:
    result = await run_list_existing_rules(FakeAutomaterService(), FakeQueryRuleService(), uuid4())

    assert "no existing" in result.lower()


async def test_list_existing_rules_filters_automaters_by_project() -> None:
    project_id = uuid4()
    other_project_automater = _automater(uuid4(), [_rule(name="Other project's rule")])
    this_project_automater = _automater(project_id, [_rule(name="High temperature")])
    automater_service = FakeAutomaterService([other_project_automater, this_project_automater])

    result = await run_list_existing_rules(automater_service, FakeQueryRuleService(), project_id)

    assert "High temperature" in result
    assert "Other project's rule" not in result
    assert "device_metrics" in result
    assert "device_id" in result


async def test_list_existing_rules_includes_query_rules() -> None:
    project_id = uuid4()
    query_rule_service = FakeQueryRuleService([_query_rule(project_id)])

    result = await run_list_existing_rules(FakeAutomaterService(), query_rule_service, project_id)

    assert "High average vibration" in result
    assert "every 15m" in result
    assert "machine_id" in result


def test_suggest_automation_builds_automater_rule_suggestion() -> None:
    project_id = uuid4()

    ack, suggestion = run_suggest_automation(
        project_id,
        {
            "kind": "automater_rule",
            "name": "High hive temperature",
            "severity": "high",
            "identifiers": ["hive_id"],
            "table": "hive_metrics",
            "conditions": [{"column": "temperature", "operator": ">", "value": 38, "join": "AND"}],
        },
    )

    assert isinstance(ack, str) and ack
    assert suggestion is not None
    assert suggestion.kind == "automater_rule"
    assert suggestion.state.project_id == project_id
    assert suggestion.state.table == "hive_metrics"
    assert suggestion.state.conditions[0].column == "temperature"


def test_suggest_automation_builds_query_rule_suggestion() -> None:
    project_id = uuid4()

    ack, suggestion = run_suggest_automation(
        project_id,
        {
            "kind": "query_rule",
            "name": "High average vibration",
            "severity": "medium",
            "identifiers": ["machine_id"],
            "sql": "SELECT machine_id FROM machine_metrics GROUP BY machine_id HAVING AVG(vibration) > 5",
            "schedule_interval": "15m",
        },
    )

    assert isinstance(ack, str) and ack
    assert suggestion is not None
    assert suggestion.kind == "query_rule"
    assert suggestion.state.schedule.interval == "15m"
    assert suggestion.state.schedule.cron is None


def test_suggest_automation_query_rule_supports_cron_schedule() -> None:
    project_id = uuid4()

    _, suggestion = run_suggest_automation(
        project_id,
        {
            "kind": "query_rule",
            "name": "Daily rollup",
            "severity": "low",
            "identifiers": [],
            "sql": "SELECT 1",
            "schedule_cron": "0 3 * * *",
        },
    )

    assert suggestion is not None
    assert suggestion.state.schedule.cron == "0 3 * * *"
    assert suggestion.state.schedule.interval is None


def test_suggest_automation_returns_error_text_and_none_on_invalid_input() -> None:
    ack, suggestion = run_suggest_automation(
        uuid4(),
        {"kind": "automater_rule", "name": "Missing table/conditions", "severity": "low", "identifiers": []},
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_automation_returns_error_text_on_unknown_kind() -> None:
    ack, suggestion = run_suggest_automation(
        uuid4(), {"kind": "bogus", "name": "x", "severity": "low", "identifiers": []}
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def _panel(**overrides) -> Panel:
    defaults: dict = {
        "title": "Hive Temperature",
        "chart": LineChart(title="Hive Temperature", x_axis="time", y_axis="temperature"),
        "query": Query(sql="SELECT time, temperature FROM hive_metrics"),
        "position": PanelPosition(x=0, y=0, width=6, height=8),
    }
    defaults.update(overrides)
    return Panel(**defaults)


def _dashboard(project_id, **overrides) -> Dashboard:
    defaults: dict = {
        "project_id": project_id,
        "name": "Apiary Overview",
        "variables": [],
        "panels": [],
    }
    defaults.update(overrides)
    return Dashboard(**defaults)


async def test_list_existing_panels_reports_none_when_project_has_no_dashboards() -> None:
    result = await run_list_existing_panels(FakeDashboardService(), uuid4())

    assert "no dashboards" in result.lower()


async def test_list_existing_panels_filters_dashboards_by_project() -> None:
    project_id = uuid4()
    other_dashboard = _dashboard(uuid4(), name="Other project's dashboard")
    this_dashboard = _dashboard(project_id, name="Apiary Overview")
    dashboard_service = FakeDashboardService([other_dashboard, this_dashboard])

    result = await run_list_existing_panels(dashboard_service, project_id)

    assert "Apiary Overview" in result
    assert "Other project's dashboard" not in result


async def test_list_existing_panels_includes_panel_and_variable_details() -> None:
    project_id = uuid4()
    dashboard = _dashboard(
        project_id,
        variables=[Variable(name="hive_id", label="Hive", table="hive_metrics", value_column="hive_id")],
        panels=[_panel()],
    )
    dashboard_service = FakeDashboardService([dashboard])

    result = await run_list_existing_panels(dashboard_service, project_id)

    assert str(dashboard.id) in result
    assert "$hive_id" in result
    assert "Hive Temperature" in result
    assert "x=time, y=temperature" in result


async def test_list_existing_panels_reports_dashboard_with_no_panels_yet() -> None:
    project_id = uuid4()
    dashboard_service = FakeDashboardService([_dashboard(project_id, panels=[])])

    result = await run_list_existing_panels(dashboard_service, project_id)

    assert "no panels yet" in result


def test_suggest_panel_builds_line_chart_suggestion() -> None:
    dashboard_id = uuid4()

    ack, suggestion = run_suggest_panel(
        {
            "dashboard_id": str(dashboard_id),
            "title": "Hive Temperature",
            "chart_type": "line",
            "sql": "SELECT time, temperature FROM hive_metrics WHERE time >= $__timeFrom AND time <= $__timeTo",
            "x_axis": "time",
            "y_axis": "temperature",
        }
    )

    assert isinstance(ack, str) and ack
    assert suggestion is not None
    assert suggestion.kind == "panel"
    assert suggestion.state.dashboard_id == dashboard_id
    assert suggestion.state.chart.type == "line"
    assert suggestion.state.chart.x_axis == "time"
    assert suggestion.state.chart.y_axis == "temperature"


def test_suggest_panel_builds_pie_chart_suggestion() -> None:
    _, suggestion = run_suggest_panel(
        {
            "dashboard_id": str(uuid4()),
            "title": "Status Breakdown",
            "chart_type": "pie",
            "sql": "SELECT status, count(*) FROM hive_metrics GROUP BY status",
            "label_field": "status",
            "value_field": "count",
        }
    )

    assert suggestion is not None
    assert suggestion.state.chart.type == "pie"
    assert suggestion.state.chart.label_field == "status"
    assert suggestion.state.chart.value_field == "count"


def test_suggest_panel_builds_gauge_chart_suggestion() -> None:
    _, suggestion = run_suggest_panel(
        {
            "dashboard_id": str(uuid4()),
            "title": "Current Weight",
            "chart_type": "gauge",
            "sql": "SELECT weight_kg FROM hive_metrics ORDER BY time DESC LIMIT 1",
            "value_field": "weight_kg",
            "min": 0,
            "max": 100,
        }
    )

    assert suggestion is not None
    assert suggestion.state.chart.type == "gauge"
    assert suggestion.state.chart.value_field == "weight_kg"


def test_suggest_panel_returns_error_text_on_missing_axis_fields() -> None:
    ack, suggestion = run_suggest_panel(
        {
            "dashboard_id": str(uuid4()),
            "title": "Incomplete",
            "chart_type": "line",
            "sql": "SELECT time, temperature FROM hive_metrics",
        }
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_panel_returns_error_text_on_invalid_dashboard_id() -> None:
    ack, suggestion = run_suggest_panel(
        {
            "dashboard_id": "not-a-uuid",
            "title": "Bad id",
            "chart_type": "line",
            "sql": "SELECT time, temperature FROM hive_metrics",
            "x_axis": "time",
            "y_axis": "temperature",
        }
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_panel_returns_error_text_on_unknown_chart_type() -> None:
    ack, suggestion = run_suggest_panel(
        {
            "dashboard_id": str(uuid4()),
            "title": "Bogus",
            "chart_type": "bogus",
            "sql": "SELECT 1",
        }
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def _dashboard_panel(**overrides) -> dict:
    defaults: dict = {
        "title": "Hive Temperature",
        "chart_type": "line",
        "sql": "SELECT time, temperature FROM hive_metrics WHERE time >= $__timeFrom AND time <= $__timeTo",
        "x_axis": "time",
        "y_axis": "temperature",
    }
    defaults.update(overrides)
    return defaults


def test_suggest_dashboard_builds_suggestion_with_variables_and_panels() -> None:
    project_id = uuid4()

    ack, suggestion = run_suggest_dashboard(
        project_id,
        {
            "name": "Apiary Overview",
            "description": "Starter dashboard",
            "variables": [
                {"name": "apiary", "label": "Apiary", "table": "hive_metrics", "value_column": "apiary_id"},
                {
                    "name": "hive",
                    "label": "Hive",
                    "table": "hive_metrics",
                    "value_column": "hive_id",
                    "predicate_column": "apiary_id",
                    "predicate_variable": "apiary",
                },
            ],
            "panels": [
                _dashboard_panel(title="Hive Temperature"),
                _dashboard_panel(
                    title="Weight by Hive",
                    chart_type="bar",
                    sql="SELECT hive_id, avg(weight_kg) AS weight_kg FROM hive_metrics "
                    "WHERE hive_id = $hive GROUP BY hive_id",
                    x_axis="hive_id",
                    y_axis="weight_kg",
                ),
                _dashboard_panel(title="Humidity Over Time", y_axis="humidity"),
            ],
        },
    )

    assert isinstance(ack, str) and "3 panels" in ack
    assert suggestion is not None
    assert suggestion.kind == "dashboard"
    assert suggestion.state.project_id == project_id
    assert suggestion.state.name == "Apiary Overview"
    assert [v.name for v in suggestion.state.variables] == ["apiary", "hive"]
    assert suggestion.state.variables[1].predicate_variable == "apiary"
    assert len(suggestion.state.panels) == 3
    assert suggestion.state.panels[1].chart.type == "bar"


def test_suggest_dashboard_builds_flat_overview_with_no_variables() -> None:
    ack, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Overview",
            "panels": [_dashboard_panel(title="A"), _dashboard_panel(title="B"), _dashboard_panel(title="C")],
        },
    )

    assert "3 panels" in ack
    assert suggestion is not None
    assert suggestion.state.variables == []


def test_suggest_dashboard_returns_error_text_on_broken_predicate_chain() -> None:
    ack, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Broken",
            "variables": [
                {
                    "name": "hive",
                    "label": "Hive",
                    "table": "hive_metrics",
                    "value_column": "hive_id",
                    "predicate_column": "apiary_id",
                    "predicate_variable": "apiary",  # never defined
                }
            ],
            "panels": [
                _dashboard_panel(title="A", sql="SELECT time, temperature FROM hive_metrics WHERE hive_id = $hive"),
                _dashboard_panel(title="B"),
                _dashboard_panel(title="C"),
            ],
        },
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_dashboard_returns_error_text_on_panel_referencing_undeclared_variable() -> None:
    # Regression: a live session had the model describe "a Machine filter
    # variable" in its own prose and write every panel's sql against
    # $machine_id, but the actual variables list was empty -- nothing
    # caught the mismatch, so the dashboard was created with every panel
    # silently returning no data ($machine_id was never substituted,
    # Postgres saw the literal token in the WHERE clause).
    ack, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Machine Monitoring",
            "panels": [
                _dashboard_panel(
                    title="Current Draw Over Time",
                    sql="SELECT time, current_draw_amps FROM machine_telemetry "
                    "WHERE time >= $__timeFrom AND time <= $__timeTo AND machine_id = $machine_id",
                    x_axis="time",
                    y_axis="current_draw_amps",
                ),
                _dashboard_panel(title="Motor Temperature"),
                _dashboard_panel(title="Vibration Over Time", y_axis="vibration_mm_s"),
            ],
        },
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()
    assert "$machine_id" in ack
    assert "undeclared" in ack.lower()


def test_suggest_dashboard_allows_panel_referencing_a_declared_variable() -> None:
    _, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Machine Monitoring",
            "variables": [
                {"name": "machine_id", "label": "Machine", "table": "machine_telemetry", "value_column": "machine_id"}
            ],
            "panels": [
                _dashboard_panel(
                    title="Current Draw Over Time",
                    sql="SELECT time, current_draw_amps FROM machine_telemetry "
                    "WHERE time >= $__timeFrom AND time <= $__timeTo AND machine_id = $machine_id",
                    x_axis="time",
                    y_axis="current_draw_amps",
                ),
                _dashboard_panel(title="Motor Temperature"),
                _dashboard_panel(title="Vibration Over Time", y_axis="vibration_mm_s"),
            ],
        },
    )

    assert suggestion is not None


def test_suggest_dashboard_returns_error_text_on_declared_but_unused_variable() -> None:
    # Regression: a live session declared a "Panel Array" variable but
    # every proposed panel was a flat fleet-wide overview that never
    # actually filtered or grouped by it -- a purely decorative variable
    # that read as broken to the user, not helpful.
    ack, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Solar Array Operations",
            "variables": [
                {"name": "array", "label": "Panel Array", "table": "solar_metrics", "value_column": "panel_array_id"}
            ],
            "panels": [
                _dashboard_panel(title="Power Output", y_axis="power_kw"),
                _dashboard_panel(title="Panel Temperature", y_axis="panel_temp_c"),
                _dashboard_panel(title="Inverter Efficiency", y_axis="efficiency"),
            ],
        },
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()
    assert "$array" in ack
    assert "no panel actually uses" in ack


def test_suggest_dashboard_allows_chain_parent_variable_used_only_indirectly() -> None:
    # A chain parent (Apiary, narrowing Hive's own options via
    # predicate_variable) is doing real work on the dashboard even without
    # its own direct $apiary reference in any panel's sql -- only the leaf
    # (Hive) needs to be directly referenced for the whole chain to count
    # as used, not every link.
    _, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Apiary Overview",
            "variables": [
                {"name": "apiary", "label": "Apiary", "table": "hive_metrics", "value_column": "apiary_id"},
                {
                    "name": "hive",
                    "label": "Hive",
                    "table": "hive_metrics",
                    "value_column": "hive_id",
                    "predicate_column": "apiary_id",
                    "predicate_variable": "apiary",
                },
            ],
            "panels": [
                _dashboard_panel(title="Hive Temperature", sql=_dashboard_panel()["sql"] + " AND hive_id = $hive"),
                _dashboard_panel(title="Apiary Overview Panel"),
                _dashboard_panel(title="Humidity Over Time", y_axis="humidity"),
            ],
        },
    )

    assert suggestion is not None
    assert [v.name for v in suggestion.state.variables] == ["apiary", "hive"]


def test_suggest_dashboard_returns_error_text_on_empty_panels() -> None:
    ack, suggestion = run_suggest_dashboard(uuid4(), {"name": "No panels", "panels": []})

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_dashboard_returns_error_text_on_single_panel() -> None:
    # Regression: a live session had the model exhaust its iteration
    # budget partway through building a dashboard, and the turn's
    # exhaustion fallback surfaced whatever suggest_dashboard call had
    # last succeeded -- a single panel -- as if it were a considered
    # final proposal. A one- or two-panel "dashboard" defeats the entire
    # point of this tool over suggest_panel, so it's rejected outright
    # rather than silently accepted.
    ack, suggestion = run_suggest_dashboard(
        uuid4(), {"name": "Too Small", "panels": [_dashboard_panel()]}
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()
    assert "at least 3 panels" in ack


def test_suggest_dashboard_builds_suggestion_with_exactly_three_panels() -> None:
    _, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Just Enough",
            "panels": [_dashboard_panel(title="A"), _dashboard_panel(title="B"), _dashboard_panel(title="C")],
        },
    )

    assert suggestion is not None
    assert len(suggestion.state.panels) == 3


def test_suggest_dashboard_returns_error_text_on_incomplete_panel() -> None:
    ack, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Incomplete",
            "panels": [
                {"title": "Incomplete", "chart_type": "line", "sql": "SELECT time FROM hive_metrics"},
                _dashboard_panel(title="Complete"),
                _dashboard_panel(title="Also Complete"),
            ],
        },
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_dashboard_returns_error_text_on_unknown_chart_type() -> None:
    ack, suggestion = run_suggest_dashboard(
        uuid4(),
        {
            "name": "Bogus",
            "panels": [
                _dashboard_panel(chart_type="bogus"),
                _dashboard_panel(title="B"),
                _dashboard_panel(title="C"),
            ],
        },
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_dashboard_returns_error_text_instead_of_crashing_on_non_object_panel() -> None:
    # Regression: a panels item that isn't an object (e.g. the model sent
    # a bare panel name/string instead of {title, chart_type, sql, ...})
    # used to raise an uncaught AttributeError ('str' has no attribute
    # 'get'), crashing the whole request instead of giving the model a
    # retryable error.
    ack, suggestion = run_suggest_dashboard(
        uuid4(), {"name": "Bad Shape", "panels": ["Total Power Output Over Time"]}
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_dashboard_error_names_the_specific_incomplete_panel() -> None:
    # Regression: a bare ValueError raised deep inside a list of several
    # panels got wrapped by Pydantic with a dump of the *entire*
    # DashboardSuggestionState (every panel, every variable) as noise
    # around the one relevant fact -- live-tested to actually cause the
    # model to give up retrying suggest_dashboard and describe the
    # dashboard in prose instead. The error must name which panel (by
    # position + title) is incomplete, and stay short regardless of how
    # many other panels are in the list.
    panels = [_dashboard_panel(title=f"Panel {i}") for i in range(4)]
    panels.append({"title": "Panel Temperature Trends", "chart_type": "line", "sql": "SELECT 1"})

    ack, suggestion = run_suggest_dashboard(uuid4(), {"name": "System Overview", "panels": panels})

    assert suggestion is None
    assert "panel 4" in ack
    assert "Panel Temperature Trends" in ack
    assert len(ack) < 300


def test_suggest_panel_tool_schema_clarifies_scatter_is_not_xy_correlation() -> None:
    # Live feedback: the model proposed a scatter panel plotting two
    # arbitrary continuous metrics against each other (irradiance vs
    # panel temperature) -- this platform's chart types don't support
    # that (PanelEditor.tsx groups scatter with line/bar as one XY family
    # sharing the same x_axis convention, always time or a grouping
    # column). The tool schema itself -- not just prose guidance -- must
    # say so, since chart_type/x_axis are filled directly from this
    # schema's own field descriptions.
    properties = SUGGEST_PANEL_TOOL["input_schema"]["properties"]
    assert "true X-Y correlation" in properties["chart_type"]["description"]
    assert "second continuous measured value" in properties["x_axis"]["description"]
