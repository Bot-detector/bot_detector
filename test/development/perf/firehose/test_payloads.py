import orjson
import pytest

from development.perf.firehose.payloads import (
    PayloadConfig,
    PlayerFlagPcts,
    build_payload_pool,
)


def test_pool_same_config_same_bytes():
    config = PayloadConfig(seed=123, pool_size=20)

    a = build_payload_pool(config)
    b = build_payload_pool(config)

    assert a == b


def test_pool_different_seed_different_bytes():
    a = build_payload_pool(PayloadConfig(seed=1, pool_size=20))
    b = build_payload_pool(PayloadConfig(seed=2, pool_size=20))

    assert a != b


def test_pool_player_ids_cycle_deterministically():
    pool = build_payload_pool(PayloadConfig(seed=9, pool_size=5))

    ids = [orjson.loads(raw)["player_data"]["id"] for raw in pool]

    assert ids == [0, 1, 2, 3, 4]


def test_pool_flag_pct_100_sets_all():
    config = PayloadConfig(
        seed=5,
        pool_size=30,
        flags=PlayerFlagPcts(
            possible_ban_pct=100.0,
            confirmed_ban_pct=100.0,
            confirmed_player_pct=100.0,
            ironman_pct=100.0,
        ),
    )

    pool = build_payload_pool(config)

    for raw in pool:
        player = orjson.loads(raw)["player_data"]
        assert player["possible_ban"] is True
        assert player["confirmed_ban"] is True
        assert player["confirmed_player"] is True
        assert player["ironman"] is True


def test_pool_flag_pct_0_clears_all():
    config = PayloadConfig(
        seed=5,
        pool_size=30,
        flags=PlayerFlagPcts(
            possible_ban_pct=0.0,
            confirmed_ban_pct=0.0,
            confirmed_player_pct=0.0,
            ironman_pct=0.0,
        ),
    )

    pool = build_payload_pool(config)

    for raw in pool:
        player = orjson.loads(raw)["player_data"]
        assert player["possible_ban"] is False
        assert player["confirmed_ban"] is False
        assert player["confirmed_player"] is False
        assert player["ironman"] is False


def test_pool_timestamps_come_from_fixed_base_time():
    pool = build_payload_pool(PayloadConfig(seed=5, pool_size=3))

    for raw in pool:
        player = orjson.loads(raw)["player_data"]
        assert player["updated_at"].startswith("2026-09-29T12:00:00")


def test_config_rejects_pct_out_of_range():
    with pytest.raises(ValueError):
        PlayerFlagPcts(possible_ban_pct=101.0)
