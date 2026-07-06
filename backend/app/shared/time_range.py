import re
from datetime import datetime, timedelta, timezone

_RANGE_RE = re.compile(r"^(\d+)([mhd])$")
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def resolve_time_range(code: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    match = _RANGE_RE.match(code)
    if not match:
        raise ValueError(f"Unsupported time range '{code}'")
    amount, unit = match.groups()
    to = now or datetime.now(timezone.utc)
    return to - timedelta(**{_UNITS[unit]: int(amount)}), to
