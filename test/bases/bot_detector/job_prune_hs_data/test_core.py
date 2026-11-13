from bot_detector.job_prune_hs_data import core


def test_drop_temp_table_sql_is_temporary_only() -> None:
    assert "DROP TEMPORARY TABLE IF EXISTS" in str(core.drop_temp_table())


def test_insert_temp_table_sql_orders_by_id() -> None:
    assert "ORDER BY id" in str(core.insert_temp_table())
