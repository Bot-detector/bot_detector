import datetime

import orjson
import pytest
from bot_detector.event_queue.structs import (
    ToScrapeBatchStruct,
    ToScrapeMessage,
    ToScrapeStruct,
)
from bot_detector.structs import MetaData, PlayerStruct
from pydantic import ValidationError


def make_player(id: int = 1) -> PlayerStruct:
    return PlayerStruct(
        id=id, name=f"player-{id}", created_at=datetime.datetime(2024, 1, 1)
    )


def make_metadata() -> MetaData:
    return MetaData(version=1, source="test")


def test_normalizes_legacy_payload_to_batch_of_one():
    payload = {
        "metadata": make_metadata().model_dump(),
        "player_data": make_player(id=7).model_dump(),
    }

    message = ToScrapeMessage.model_validate(payload)

    assert len(message.players) == 1
    assert message.players[0].id == 7


def test_normalization_preserves_metadata_version():
    legacy = ToScrapeMessage.model_validate(
        {
            "metadata": {"version": 1, "source": "test"},
            "player_data": make_player().model_dump(),
        }
    )
    batched = ToScrapeMessage.model_validate(
        {
            "metadata": {"version": 2, "source": "test"},
            "players": [make_player().model_dump()],
        }
    )

    # metadata rides along untouched: v1 = legacy single, v2 = batched
    assert legacy.metadata.version == 1
    assert batched.metadata.version == 2


def test_dispatch_is_by_shape_not_version_int():
    # a players-shaped payload with a legacy version int still parses
    payload = {
        "metadata": {"version": 1, "source": "test"},
        "players": [make_player(id=8).model_dump()],
    }

    message = ToScrapeMessage.model_validate(payload)

    assert len(message.players) == 1
    assert message.players[0].id == 8


def test_batched_payload_passes_through():
    payload = {
        "metadata": make_metadata().model_dump(),
        "players": [make_player(id=1).model_dump(), make_player(id=2).model_dump()],
    }

    message = ToScrapeMessage.model_validate(payload)

    assert [p.id for p in message.players] == [1, 2]


def test_normalizes_legacy_struct_instance():
    legacy = ToScrapeStruct(metadata=make_metadata(), player_data=make_player(id=3))

    message = ToScrapeMessage.model_validate(legacy)

    assert len(message.players) == 1
    assert message.players[0].id == 3


def test_normalizes_batch_struct_instance():
    batch = ToScrapeBatchStruct(metadata=make_metadata(), players=[make_player(id=4)])

    message = ToScrapeMessage.model_validate(batch)

    assert len(message.players) == 1
    assert message.players[0].id == 4


def test_message_instance_passes_through_without_copy():
    message = ToScrapeMessage(metadata=make_metadata(), players=[make_player(id=5)])

    result = ToScrapeMessage.model_validate(message)

    assert result is message


def test_serialized_shape_is_batched():
    message = ToScrapeMessage(metadata=make_metadata(), players=[make_player(id=6)])

    dumped = message.model_dump()

    assert set(dumped) == {"metadata", "players"}
    assert len(dumped["players"]) == 1


def test_payload_without_players_or_player_data_is_rejected():
    with pytest.raises(ValidationError):
        ToScrapeMessage.model_validate({"metadata": make_metadata().model_dump()})


def test_batch_struct_rejects_legacy_payload():
    # the producer-side model is strict: only the consumer-facing
    # ToScrapeMessage normalizes legacy shapes
    with pytest.raises(ValidationError):
        ToScrapeBatchStruct.model_validate(
            {
                "metadata": make_metadata().model_dump(),
                "player_data": make_player().model_dump(),
            }
        )


def test_slim_batch_payload_round_trips_to_full_message():
    """Exclude-none serialization must not change the rehydrated batch.

    Producers serialize batches with exclude_none=True, dropping the
    always-null PlayerStruct optionals (ironman, hardcore_ironman,
    ultimate_ironman, normalized_name); consumers validate with the
    same pydantic model, whose Optionals default back to None.
    """
    player = PlayerStruct(
        id=9,
        name="player-9",
        created_at=datetime.datetime(2024, 1, 1),
        ironman=None,
        hardcore_ironman=None,
        ultimate_ironman=None,
        normalized_name=None,
    )
    full = ToScrapeBatchStruct(metadata=make_metadata(), players=[player])

    slim_bytes = orjson.dumps(full.model_dump(exclude_none=True))

    # the slim payload really omits the null-valued keys
    dumped = orjson.loads(slim_bytes)
    slim_player = dumped["players"][0]
    assert "ironman" not in slim_player
    assert "hardcore_ironman" not in slim_player
    assert "ultimate_ironman" not in slim_player
    assert "normalized_name" not in slim_player

    rehydrated = ToScrapeMessage.model_validate(dumped)
    # slim bytes and full bytes rehydrate to the same message
    assert rehydrated == ToScrapeMessage.model_validate(full.model_dump())
    assert rehydrated.players[0] == player


def test_slim_batch_payload_keeps_set_optional_fields():
    """exclude_none drops nulls only: set optionals must survive."""
    player = PlayerStruct(
        id=10,
        name="player-10",
        created_at=datetime.datetime(2024, 1, 1),
        ironman=True,
    )
    full = ToScrapeBatchStruct(metadata=make_metadata(), players=[player])

    slim_bytes = orjson.dumps(full.model_dump(exclude_none=True))

    rehydrated = ToScrapeMessage.model_validate(orjson.loads(slim_bytes))

    assert rehydrated.players[0].ironman is True
    assert rehydrated == ToScrapeMessage.model_validate(full.model_dump())
