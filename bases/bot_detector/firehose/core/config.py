from pydantic_settings import BaseSettings, SettingsConfigDict


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


SETTINGS = Settings()
