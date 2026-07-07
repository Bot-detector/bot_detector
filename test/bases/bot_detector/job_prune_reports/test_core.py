from bot_detector.job_prune_reports import core


def test_settings_defaults():
    settings = core.Settings()
    assert settings.REPORT_RETENTION_DAYS == 90
    assert settings.BATCH_SIZE == 10_000


def test_entrypoints_exist():
    assert callable(core.run)
    assert callable(core.run_async)
    assert callable(core.main)
