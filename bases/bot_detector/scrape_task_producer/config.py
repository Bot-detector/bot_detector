from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    LIMIT: int = 10_000
    MAX_LAG: int = 100_000
    NORMAL_DAY_LIMIT = 1
    POSSIBLE_BAN_DAY_LIMIT = 7
    CONFIRMED_BAN_DAY_LIMIT = 14
