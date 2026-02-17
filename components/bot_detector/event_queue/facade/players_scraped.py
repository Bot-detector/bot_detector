from bot_detector.event_queue.adapters.kafka import KafkaConfig
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.structs import ScrapedStruct

from .base import BackendType, BaseConsumerFacade, BaseProducerFacade, BaseQueueFacade


class PlayersScrapedProducer(BaseProducerFacade[ScrapedStruct]):
    def __init__(
        self,
        bootstrap_servers: str | None,
        max_async_actions: int = 10,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        _ = max_async_actions
        super().__init__(
            ScrapedStruct,
            "players.scraped",
            lambda message: str(message.player_data.id % 10),
            bootstrap_servers,
            backend_type,
            backend_config,
        )


class PlayersScrapedConsumer(BaseConsumerFacade[ScrapedStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            ScrapedStruct,
            "players.scraped",
            group_id,
            bootstrap_servers,
            enable_auto_commit,
            backend_type,
            backend_config,
        )


class PlayersScrapedQueue(BaseQueueFacade[ScrapedStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            ScrapedStruct,
            "players.scraped",
            lambda message: str(message.player_data.id % 10),
            group_id,
            bootstrap_servers,
            enable_auto_commit,
            backend_type,
            backend_config,
        )
