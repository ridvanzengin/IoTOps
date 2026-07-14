import httpx
import pytest

from app.ai.models import AiVariableHint
from app.ai.service import AiService
from app.shared.exceptions import AiGenerationError
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.telemetry.fakes import FakePool


def _telemetry_service() -> TelemetryService:
    pool = FakePool(
        tables=["device_metrics"],
        schema={
            "device_metrics": [
                {"column_name": "temperature", "data_type": "double precision", "is_nullable": "YES"}
            ]
        },
    )
    return TelemetryService(repository=TelemetryRepository(pool))


def _service(handler) -> AiService:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AiService(
        telemetry_service=_telemetry_service(),
        http_client=client,
        base_url="http://ollama",
        model="gemma4:latest",
    )


async def test_generate_sql_strips_markdown_fences() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"response": "```sql\nSELECT * FROM device_metrics\n```"}
        )

    sql = await _service(handler).generate_sql("show me all metrics")

    assert sql == "SELECT * FROM device_metrics"


async def test_generate_sql_sends_configured_model() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"response": "SELECT 1"})

    await _service(handler).generate_sql("count rows")

    assert b'"model":"gemma4:latest"' in captured["body"]


async def test_generate_sql_rejects_non_select_response() -> None:
    # Wrapped into AiGenerationError, not left as InvalidQueryError -- the
    # AI failing to return usable SQL is a different failure than the
    # *user* hand-writing bad SQL, and deserves a message that says so.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "DELETE FROM device_metrics"})

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_sql("delete everything")


async def test_generate_sql_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_sql("anything")


async def test_generate_sql_wraps_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_sql("anything")


async def test_generate_sql_forwards_variable_hints_into_prompt() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"response": "SELECT 1"})

    await _service(handler).generate_sql(
        "temperature for the selected hive",
        variables=[AiVariableHint(name="hive_id", label="Hive")],
    )

    assert b"$hive_id" in captured["body"]


async def test_generate_query_rule_sql_strips_markdown_fences() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"response": "```sql\nSELECT device_id FROM device_metrics GROUP BY device_id\n```"}
        )

    sql = await _service(handler).generate_query_rule_sql("devices with high average temperature")

    assert sql == "SELECT device_id FROM device_metrics GROUP BY device_id"


async def test_generate_query_rule_sql_uses_the_query_rule_prompt() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"response": "SELECT 1"})

    await _service(handler).generate_query_rule_sql("devices with high average temperature")

    # The query-rule-specific framing, not the Panel/dashboard one -- a
    # cheap way to confirm this went through build_query_rule_sql_prompt,
    # not build_sql_prompt, without re-testing the prompt's own content.
    assert b"scheduled monitoring rule" in captured["body"]


async def test_generate_query_rule_sql_rejects_non_select_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "DELETE FROM device_metrics"})

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_query_rule_sql("delete everything")


async def test_generate_query_rule_sql_gives_actionable_message_on_invalid_sql() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "I need more information about which table."})

    with pytest.raises(AiGenerationError, match="more specific"):
        await _service(handler).generate_query_rule_sql("average humidity is higher than 60")


async def test_generate_query_rule_sql_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_query_rule_sql("anything")


async def test_generate_query_rule_sql_forwards_identifiers_hint_into_prompt() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"response": "SELECT 1"})

    await _service(handler).generate_query_rule_sql("average humidity per hive", identifiers=["hive_id"])

    assert b"hive_id" in captured["body"]
