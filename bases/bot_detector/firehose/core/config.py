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
    # per-topic access as two allowlists: anonymous clients stream
    # public_topics, keyed identities (valid api key + `firehose.<topic>`
    # scope) stream keyed_topics; a topic may be in both or in neither
    # (disabled). csv in env: PUBLIC_TOPICS=a,b KEYED_TOPICS=c
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
