from pathlib import Path

from pydantic_settings import BaseSettings


class KafkaSeederConfig(BaseSettings):
    KAFKA_BROKER: str = "localhost:9094"

    SEED_PLAYERS: int = 100
    SEED_SCRAPES_PER_PLAYER: int = 30
    SEED_REPORTS: int = 100_000
    SEED_BANNED: int = 0

    RESET_TOPICS: bool = False
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
