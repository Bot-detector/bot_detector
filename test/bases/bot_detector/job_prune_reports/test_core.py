import pytest
from bot_detector.job_prune_reports import core
from pydantic import ValidationError


def test_settings_defaults():
    settings = core.Settings()
    assert settings.REPORT_RETENTION_DAYS == 90
    assert settings.BATCH_SIZE == 10_000


def test_settings_rejects_zero_batch_size():
    with pytest.raises(ValidationError):
        core.Settings(BATCH_SIZE=0)


def test_entrypoints_exist():
    assert callable(core.run)
    assert callable(core.run_async)
    assert callable(core.main)


def test_run_exits_nonzero_on_failure(monkeypatch):
    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(core, "run_async", boom)
    with pytest.raises(SystemExit) as exc_info:
        core.run()
    assert exc_info.value.code == 1
