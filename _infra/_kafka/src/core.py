import json
import random
import sys

from kafka import KafkaProducer

sys.path.insert(0, "/app/_shared")

from config import KafkaSeederConfig, load_names
from seeders.players_scraped import create_players_scraped
from seeders.players_to_scrape import create_players_to_scrape
from topics import create_topics

config = KafkaSeederConfig()


def create_kafka_producer(kafka_broker: str | list):
    return KafkaProducer(
        bootstrap_servers=kafka_broker,
        value_serializer=lambda x: json.dumps(x).encode(),
        acks="all",
        batch_size=1,
    )


def seed_players_to_scrape(producer: KafkaProducer, names: list[str], count: int):
    print(f"Seeding {count} players to players.to_scrape...")
    for to_scrape in create_players_to_scrape(names=names, count=count):
        producer.send(
            topic="players.to_scrape",
            value=to_scrape.model_dump(mode="json"),
        )
        print(f"  -> {to_scrape.player_data.name}")
    producer.flush()
    print("Done seeding players.to_scrape")


def seed_players_scraped(
    producer: KafkaProducer,
    names: list[str],
    player_count: int,
    scrapes_per_player: int,
):
    print(
        f"Seeding {player_count} players with {scrapes_per_player} scrapes each to players.scraped..."
    )

    players = []
    for to_scrape in create_players_to_scrape(names=names, count=player_count):
        players.append(to_scrape.player_data)

    scraped_data = list(create_players_scraped(players, scrapes_per_player))
    random.shuffle(scraped_data)

    for scraped in scraped_data:
        producer.send(
            topic="players.scraped",
            value=scraped.model_dump(mode="json"),
        )
        scrape_date = (
            scraped.highscore_data.scrape_date if scraped.highscore_data else "N/A"
        )
        print(f"  -> {scraped.player_data.name} @ {scrape_date}")
    producer.flush()
    print("Done seeding players.scraped")


def main():
    random.seed(config.RANDOM_SEED)

    names = load_names(config.NAMES_FILE)

    create_topics(
        kafka_broker=config.KAFKA_BROKER,
        reset=config.RESET_TOPICS,
    )

    producer = create_kafka_producer(kafka_broker=config.KAFKA_BROKER)

    if config.SEED_PLAYERS > 0:
        seed_players_to_scrape(
            producer=producer,
            names=names,
            count=config.SEED_PLAYERS,
        )
        seed_players_scraped(
            producer=producer,
            names=names,
            player_count=config.SEED_PLAYERS,
            scrapes_per_player=config.SEED_SCRAPES_PER_PLAYER,
        )

    if config.SEED_REPORTS > 0:
        print("Report seeding not yet implemented")


if __name__ == "__main__":
    main()
