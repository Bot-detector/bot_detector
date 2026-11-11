from typing import Any

from bot_detector.structs._metadata import MetaData
from bot_detector.structs.player import PlayerStruct
from pydantic import BaseModel, model_validator


class ToScrapeStruct(BaseModel):
    """Legacy single-name payload (metadata version 1) on players.to_scrape.

    Still emitted by infra seeders and producers predating batching,
    so consumers must keep accepting it during a rolling deploy.
    """

    metadata: MetaData
    player_data: PlayerStruct


class ToScrapeBatchStruct(BaseModel):
    """Batched payload (metadata version 2) on players.to_scrape:
    N names in one message.

    One kafka message pays one fetch RTT and one offset commit for the
    whole batch; the consumer fans out per name.
    """

    metadata: MetaData
    players: list[PlayerStruct]


class ToScrapeMessage(ToScrapeBatchStruct):
    """Consumer-facing view of players.to_scrape.

    Normalizes both payload versions so the scraper always iterates
    .players (size 1..N): version 2 batched payloads pass through,
    version 1 legacy single-name payloads become a batch of one.
    Dispatch is by payload shape, not the version int, so messages are
    parsed even if metadata.version is missing or mislabeled.
    """

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, data: Any) -> Any:
        """{"metadata", "players"} stays; {"metadata", "player_data"}
        becomes a batch of one; BaseModel instances (memory backend,
        sims) are reshaped via model_dump."""
        if isinstance(data, BaseModel):
            if isinstance(data, cls):
                return data
            return cls._normalize_payload(data.model_dump())
        if isinstance(data, dict) and "players" not in data and "player_data" in data:
            return {**data, "players": [data["player_data"]]}
        return data
