import logging
from random import randint
from typing import Any

import orjson
import pytest
from bot_detector.kafka.repositories.reports_to_insert import (
    RepoReportsToInsertConsumer,
)
from mockafka import FakeAdminClientImpl, FakeConsumer, FakeProducer
from mockafka.admin_client import NewTopic
from mockafka.aiokafka import FakeAIOKafkaConsumer, FakeAIOKafkaProducer
from mockafka.kafka_store import KafkaStore
from mockafka.message import Message

from test.components.bot_detector.kafka.test_players_to_scrape import fake_consumer

logger = logging.getLogger(__name__)


async def setup_kafka(topics: list[str], messages: dict[str, Any]) -> KafkaStore:
    # Create topic
    admin = FakeAdminClientImpl(clean=True)
    admin.create_topics([NewTopic(topic=topic, num_partitions=1) for topic in topics])

    # Produce messages
    producer = FakeAIOKafkaProducer()
    producer.kafka = admin.kafka

    await producer.start()
    for topic, msgs in messages.items():
        for msg in msgs:
            await producer.send(
                topic=topic,
                key=b"",
                value=orjson.dumps(msg),
                partition=0,
            )
    await producer.stop()
    return producer.kafka


@pytest.mark.asyncio
async def test_sanity_kafka_store():
    kafka = await setup_kafka(
        topics=["reports.to_insert"],
        messages={
            "reports.to_insert": [
                {
                    "metadata": {"version": 1, "source": "api_public"},
                    "report": {
                        "region_id": 12598,
                        "x_coord": 3167,
                        "y_coord": 3490,
                        "z_coord": 0,
                        "ts": 1763909384,
                        "manual_detect": 0,
                        "on_members_world": 1,
                        "on_pvp_world": 0,
                        "world_number": 490,
                        "equipment": {
                            "equip_head_id": None,
                            "equip_amulet_id": None,
                            "equip_torso_id": None,
                            "equip_legs_id": None,
                            "equip_boots_id": None,
                            "equip_cape_id": None,
                            "equip_hands_id": None,
                            "equip_weapon_id": None,
                            "equip_shield_id": None,
                        },
                        "equip_ge_value": 0,
                        "reporter_id": 398265,
                        "reported_id": 233134407,
                    },
                }
            ]
        },
    )
    message = kafka.get_message(topic="reports.to_insert", partition=0, offset=0)
    assert message is not None


@pytest.mark.asyncio
async def test_sanity_AIOKafkaConsumer():
    kafka = await setup_kafka(
        topics=["reports.to_insert"],
        messages={
            "reports.to_insert": [
                {
                    "metadata": {"version": 1, "source": "api_public"},
                    "report": {
                        "region_id": 12598,
                        "x_coord": 3167,
                        "y_coord": 3490,
                        "z_coord": 0,
                        "ts": 1763909384,
                        "manual_detect": 0,
                        "on_members_world": 1,
                        "on_pvp_world": 0,
                        "world_number": 490,
                        "equipment": {
                            "equip_head_id": None,
                            "equip_amulet_id": None,
                            "equip_torso_id": None,
                            "equip_legs_id": None,
                            "equip_boots_id": None,
                            "equip_cape_id": None,
                            "equip_hands_id": None,
                            "equip_weapon_id": None,
                            "equip_shield_id": None,
                        },
                        "equip_ge_value": 0,
                        "reporter_id": 398265,
                        "reported_id": 233134407,
                    },
                }
            ]
        },
    )
    # Create an instance of FakeAIOKafkaConsumer
    consumer = FakeAIOKafkaConsumer()
    consumer.kafka = kafka
    consumer.subscribe(topics=["reports.to_insert"])
    await consumer.start()
    results = await consumer.getmany()
    assert results is not None


@pytest.mark.asyncio
async def test_consume_many_with_mocked_consumer():
    kafka = await setup_kafka(
        topics=["reports.to_insert"],
        messages={
            "reports.to_insert": [
                {
                    "metadata": {"version": 1, "source": "api_public"},
                    "report": {
                        "region_id": 12598,
                        "x_coord": 3167,
                        "y_coord": 3490,
                        "z_coord": 0,
                        "ts": 1763909384,
                        "manual_detect": 0,
                        "on_members_world": 1,
                        "on_pvp_world": 0,
                        "world_number": 490,
                        "equipment": {
                            "equip_head_id": None,
                            "equip_amulet_id": None,
                            "equip_torso_id": None,
                            "equip_legs_id": None,
                            "equip_boots_id": None,
                            "equip_cape_id": None,
                            "equip_hands_id": None,
                            "equip_weapon_id": None,
                            "equip_shield_id": None,
                        },
                        "equip_ge_value": 0,
                        "reporter_id": 398265,
                        "reported_id": 233134407,
                    },
                }
            ]
        },
    )
    # Create an instance of FakeAIOKafkaConsumer
    consumer = FakeAIOKafkaConsumer()
    consumer.kafka = kafka
    consumer.subscribe(topics=["reports.to_insert"])
    await consumer.start()

    repo = RepoReportsToInsertConsumer(
        group_id="test_group",
        bootstrap_servers="localhost:9092",
    )
    # patch the consumer with a mocked one
    repo.set_consumer(consumer)
    messages = await repo.consume_many()
    assert len(messages) > 0
