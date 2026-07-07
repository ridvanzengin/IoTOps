from datetime import datetime, timedelta, timezone

import pytest

from app.shared.time_range import resolve_time_range


@pytest.mark.parametrize(
    ("code", "expected_delta"),
    [
        ("15m", timedelta(minutes=15)),
        ("1h", timedelta(hours=1)),
        ("6h", timedelta(hours=6)),
        ("24h", timedelta(hours=24)),
        ("7d", timedelta(days=7)),
    ],
)
def test_resolves_supported_codes(code: str, expected_delta: timedelta) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    time_from, time_to = resolve_time_range(code, now=now)

    assert time_to == now
    assert time_from == now - expected_delta


def test_defaults_to_current_time_when_now_not_given() -> None:
    before = datetime.now(timezone.utc)

    _, time_to = resolve_time_range("1h")

    assert before <= time_to <= datetime.now(timezone.utc)


def test_rejects_unsupported_code() -> None:
    with pytest.raises(ValueError, match="Unsupported time range"):
        resolve_time_range("3w")
