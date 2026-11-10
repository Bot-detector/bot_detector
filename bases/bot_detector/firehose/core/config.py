from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# per-topic anonymous access; topics missing from the map are public
TopicAccess = Literal["public", "keyed"]


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
    # anonymous access per topic; "keyed" requires a valid api key with
    # the `firehose.<topic>` scope, "public" streams to anonymous too.
    # topics missing from the map are public. json object in env:
    # TOPIC_ACCESS='{"reports.to_insert": "keyed"}'
    topic_access: dict[str, TopicAccess] = {"reports.to_insert": "keyed"}


SETTINGS = Settings()
