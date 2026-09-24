from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 5000

    # hardcoded for now; swap for DB-backed validation later
    # override via env: API_KEYS='{"key": "system-name"}'
    api_keys: dict[str, str] = Field(
        default_factory=lambda: {
            "changeme-key-one": "system-one",
            "changeme-key-two": "system-two",
        }
    )

    # discord oauth2 (authorization code grant)
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = "http://localhost:8000/login/callback"


SETTINGS = Settings()
