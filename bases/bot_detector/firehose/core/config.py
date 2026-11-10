from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 5000
    metrics_port: int = 8000
    # browser clients on other origins (e.g. the firehose frontend pointing
    # at localhost or the live endpoint); json list in env:
    # CORS_ORIGINS='["https://example.com"]'; ["*"] = any origin, no
    # credentials (X-API-Key header only, never cookies)
    cors_origins: list[str] = ["*"]
    # new subscribers cannot be kicked for backpressure during this
    # window: connect ramps fill inboxes while joiners arrive, not
    # because a client is slow. within the grace a full inbox drops
    # messages instead of kicking
    kick_grace_s: float = 30.0
    # per-topic anonymous access: keyed topics need a valid api key with
    # the `firehose.<topic>` scope, public topics stream to anonymous
    # too; together they must cover the catalog exactly. csv in env:
    # PUBLIC_TOPICS=players.scraped,players.not_found KEYED_TOPICS=reports.to_insert
    public_topics: Annotated[set[str], NoDecode] = {
        "players.scraped",
        "players.not_found",
        "predictions.to_insert",
    }
    keyed_topics: Annotated[set[str], NoDecode] = {"reports.to_insert"}

    @field_validator("public_topics", "keyed_topics", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return {part.strip() for part in value.split(",") if part.strip()}
        return value


SETTINGS = Settings()
