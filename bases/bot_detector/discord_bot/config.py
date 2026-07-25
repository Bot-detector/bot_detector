
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DISCORD_TOKEN: str = Field(default=...)
    COMMAND_PREFIX: str = Field(default="!")
    API_TOKEN: str | None = Field(default=None)
    API_USER: str | None = Field(default="Discord_bot")
    DATABASE_URL: str | None = Field(default=None)
    API_URL: str | None = Field(default=None)
    WEBHOOK: str | None = Field(default=None)
    OSRS_ITEMS_USER_AGENT: str = Field(default=...)
