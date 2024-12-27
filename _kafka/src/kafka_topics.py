import os

from kafka.admin import KafkaAdminClient, NewTopic


def create_topics():
    # Get the Kafka broker address from the environment variable
    kafka_broker = os.environ.get("KAFKA_BROKER", "localhost:9094")

    # Create Kafka topics
    admin_client = KafkaAdminClient(bootstrap_servers=kafka_broker)

    topics = admin_client.list_topics()
    print("existing topics", topics)

    if not topics == []:
        admin_client.delete_topics(topics)

    res = admin_client.create_topics(
        [
            # producer: automation (TBD)
            # consumer: hiscore_scraper
            NewTopic(
                name="players.to_scrape",
                num_partitions=4,
                replication_factor=1,
            ),
            # producer: hiscore_scraper
            # producer: runemetrics_scraper
            # consumer: hiscore_worker
            NewTopic(
                name="players.scraped",
                num_partitions=4,
                replication_factor=1,
            ),
            # producer: hiscore_scraper
            # consumer: runemetrics_scraper
            NewTopic(
                name="players.not_found",
                num_partitions=4,
                replication_factor=1,
            ),
            # producer: public_api
            # consumer: report_worker
            NewTopic(
                name="reports.to_insert",
                num_partitions=4,
                replication_factor=1,
            ),
        ]
    )

    print("created_topic", res)

    topics = admin_client.list_topics()
    print("all topics", topics)
    return
