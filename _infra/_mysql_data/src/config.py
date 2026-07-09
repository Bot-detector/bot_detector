from pathlib import Path

from pydantic_settings import BaseSettings


class MySQLSeederConfig(BaseSettings):
    DATABASE_URL: str
    DEBUG: bool = False

    SEED_PLAYERS: int = 100
    SEED_REPORTS: int = 0
    SEED_PREDICTIONS: int = 0
    SEED_BANNED: int = 0
    SEED_AGED_REPORTS: int = 0
    SEED_RETENTION_DAYS: int = 90

    SKIP_IF_EXISTING: bool = True
    SKIP_THRESHOLD: int = 100
    RANDOM_SEED: int = 42

    NAMES_FILE: str = "/app/_shared/names.txt"


def load_names(names_file: str) -> list[str]:
    path = Path(names_file)
    if not path.exists():
        raise FileNotFoundError(f"Names file not found: {names_file}")

    names = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(line)
    return names
