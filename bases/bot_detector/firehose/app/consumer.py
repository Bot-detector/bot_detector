import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import QueueConsumer, QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.firehose.app.auth.auth import ANONYMOUS_USER, AuthUser
from bot_detector.firehose.core.config import Settings
from pydantic import BaseModel

logger = logging.getLogger(__name__)

ANONYMOUS_CONSUMER_GROUP_PREFIX = "fh-anonymous"
KEYED_CONSUMER_GROUP_PREFIX = "fh"

# hardcoded catalog: topics exposed by the firehose -> message model
# (add entries here to expose more topics; each needs a `firehose.<topic>`
# permission for keyed access)
TOPIC_MODELS: dict[str, type[BaseModel]] = {
    "players.scraped": ScrapedStruct,
}

ALLOWED_TOPICS: list[str] = list(TOPIC_MODELS.keys())


async def stream(
    consumer: QueueConsumer[BaseModel],
) -> AsyncIterator[BaseModel]:
    """Yield messages as received; abort on consumer errors."""
    while True:
        message = await consumer.get_one()
        if message is None:
            continue
        if isinstance(message, Exception):
            raise message
        yield message


@runtime_checkable
class QueueRepoProtocol(Protocol):
    def resolve_consumer_group(self, user: AuthUser, topic: str) -> str: ...

    def create_consumer(
        self, user: AuthUser, topic: str
    ) -> QueueConsumer[Any] | Exception: ...


class QueueRepo:
    """Kafka consumer access for the firehose.

    Anonymous users share a per-topic group; each authenticated user gets
    a dedicated group per topic, so its stream is independent.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._bootstrap_servers = KafkaSettings().bootstrap_servers

    def resolve_consumer_group(self, user: AuthUser, topic: str) -> str:
        if user.name == ANONYMOUS_USER:
            return f"{ANONYMOUS_CONSUMER_GROUP_PREFIX}-{topic}"
        return (
            f"{KEYED_CONSUMER_GROUP_PREFIX}-{topic}-"
            f"{user.name.removeprefix('discord_')}"
        )

    def create_consumer(
        self, user: AuthUser, topic: str
    ) -> QueueConsumer[BaseModel] | Exception:
        if topic not in TOPIC_MODELS:
            return ValueError(f"unknown topic: {topic}")
        anonymous = user.name == ANONYMOUS_USER
        config = KafkaConfig(
            topic=topic,
            bootstrap_servers=self._bootstrap_servers,
            consumer=True,
            consumer_config=KafkaConsumerConfig(
                group_id=self.resolve_consumer_group(user=user, topic=topic),
                # anonymous joins an existing group (committed offsets), a new
                # keyed group replays the topic from the earliest retained offset
                auto_offset_reset="latest" if anonymous else "earliest",
                enable_auto_commit=True,
            ),
        )
        queue = QueueFactory.create_queue(
            model=TOPIC_MODELS[topic],
            queue_type="consumer",
            backend_type="kafka",
            config=config,
        )
        if isinstance(queue, QueueProducer):
            # unreachable with queue_type="consumer", kept for type narrowing
            return ValueError(f"expected consumer queue, got producer: {type(queue)}")
        return queue
