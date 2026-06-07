from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_uri: str = Field(default=...)
    base_path: str = Field(default=...)

    class Config:
        env_file = ".env"
