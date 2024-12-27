import json
import os

import kafka_data
import kafka_topics
from kafka import KafkaProducer


def create_kafka_producer():
    # Get the Kafka broker address from the environment variable
    kafka_broker = os.environ.get("KAFKA_BROKER", "localhost:9094")

    # Create the Kafka producer
    producer = KafkaProducer(
        bootstrap_servers=kafka_broker,
        value_serializer=lambda x: json.dumps(x).encode(),
        acks="all",
        # retries=100,
        batch_size=1,
    )
    return producer


def insert_data(producer: KafkaProducer):
    player_generator = kafka_data.create_player()
    for player in player_generator:
        print(player.name)
        producer.send(topic="players.to_scrape", value=player.model_dump())


def main():
    kafka_topics.create_topics()
    producer = create_kafka_producer()
    insert_data(producer=producer)


if __name__ == "__main__":
    main()
