from bot_detector.job_prune_hs_data import core


def test_drop_temp_table_sql_is_temporary_only() -> None:
    assert "DROP TEMPORARY TABLE IF EXISTS" in str(core.drop_temp_table())
