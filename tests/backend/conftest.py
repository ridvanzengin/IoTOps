import pytest

from app.config import settings


# settings.demo defaults to False, but force it explicitly for every test
# regardless -- this suite assumes full read/write access, and an
# accidental DEMO=true in the shell running pytest shouldn't be able to
# break it. test_demo_mode.py re-enables it locally where it's actually
# exercising the guard.
@pytest.fixture(autouse=True)
def _demo_mode_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo", False)
