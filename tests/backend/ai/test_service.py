import httpx
import pytest

from app.ai.models import AiVariableHint
from app.ai.service import AiService
from app.shared.exceptions import AiGenerationError, InvalidQueryError
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
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "DELETE FROM device_metrics"})

    with pytest.raises(InvalidQueryError):
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
