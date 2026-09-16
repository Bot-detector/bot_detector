from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from bot_detector.scrape_task_producer.core import FetchParams, produce_players
from bot_detector.structs import PlayerStruct
from prometheus_client import REGISTRY


def _sample(name: str, labels: dict[str, str] | None = None) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def _player(player_id: int) -> PlayerStruct:
    return PlayerStruct(
        id=player_id,
        name=f"player{player_id}",
        created_at=datetime.now(tz=UTC),
    )


def test_set_step_increments_transition_counter():
    before = (
        _sample(
            "scrape_task_producer_step_transitions_total",
            {"from_step": "normal", "to_step": "possible_ban"},
        )
        or 0
    )

    fp = FetchParams(step="normal", days=20)
    fp.set_step("possible_ban")

    assert fp.step == "possible_ban"
    assert (
        _sample(
            "scrape_task_producer_step_transitions_total",
            {"from_step": "normal", "to_step": "possible_ban"},
        )
        or 0
    ) == before + 1


@pytest.mark.asyncio
async def test_produce_players_increments_produced_counter():
    players = [_player(i) for i in range(3)]
    before = _sample("scrape_task_producer_players_produced_total") or 0

    await produce_players(players=players, player_queue=AsyncMock())

    assert (_sample("scrape_task_producer_players_produced_total") or 0) == before + 3
