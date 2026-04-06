from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DISCORD_TOKEN: str = Field(default=...)
    COMMAND_PREFIX: str = Field(default="!")
    API_TOKEN: Optional[str] = Field(default=None)
    SQL_URI: Optional[str] = Field(default=None)
    API_URL: Optional[str] = Field(default=None)
    WEBHOOK: Optional[str] = Field(default=None)
    OSRS_ITEMS_USER_AGENT: str = Field(default=...)
