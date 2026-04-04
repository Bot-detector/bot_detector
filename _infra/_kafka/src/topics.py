from kafka.admin import KafkaAdminClient, NewTopic

from config import KafkaSeederConfig

config = KafkaSeederConfig()


TOPICS = [
    NewTopic(
        name="players.to_scrape",
        num_partitions=4,
        replication_factor=1,
    ),
    NewTopic(
        name="players.scraped",
        num_partitions=4,
        replication_factor=1,
    ),
    NewTopic(
        name="players.not_found",
        num_partitions=4,
        replication_factor=1,
    ),
    NewTopic(
        name="reports.to_insert",
        num_partitions=4,
        replication_factor=1,
    ),
    NewTopic(
        name="data.to_predict",
        num_partitions=4,
        replication_factor=1,
    ),
]


def create_topics(kafka_broker: str, reset: bool = False):
    admin_client = KafkaAdminClient(bootstrap_servers=kafka_broker)

    existing_topics = admin_client.list_topics()
    print(f"Existing topics: {existing_topics}")

    if reset and existing_topics:
        print(f"Deleting topics: {existing_topics}")
        admin_client.delete_topics(existing_topics)

    topics_to_create = []
    for topic in TOPICS:
        if topic.name not in admin_client.list_topics():
            topics_to_create.append(topic)

    if topics_to_create:
        res = admin_client.create_topics(topics_to_create)
        print(f"Created topics: {res}")

    all_topics = admin_client.list_topics()
    print(f"All topics: {all_topics}")
    return all_topics
