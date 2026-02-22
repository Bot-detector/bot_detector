from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bootstrap_servers: str = Field(default=...)
