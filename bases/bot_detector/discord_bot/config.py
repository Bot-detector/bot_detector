from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    TOKEN: str
    COMMAND_PREFIX: str = "!"
    API_TOKEN: str | None = None
    SQL_URI: str | None = None
    API_URL: str | None = None
    WEBHOOK: str | None = None
    OSRS_ITEMS_USER_AGENT: str = "discord:<name#id>"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
