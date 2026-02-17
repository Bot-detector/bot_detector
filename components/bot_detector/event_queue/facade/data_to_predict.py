from bot_detector.event_queue.adapters.kafka import KafkaConfig
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.structs import DataToPredictStruct

from .base import BackendType, BaseConsumerFacade, BaseProducerFacade, BaseQueueFacade


class DataToPredictProducer(BaseProducerFacade[DataToPredictStruct]):
    def __init__(
        self,
        bootstrap_servers: str | None,
        max_async_actions: int = 10,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        _ = max_async_actions
        super().__init__(
            DataToPredictStruct,
            "data.to_predict",
            lambda message: str(message.player_id % 10),
            bootstrap_servers,
            backend_type,
            backend_config,
        )


class DataToPredictConsumer(BaseConsumerFacade[DataToPredictStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            DataToPredictStruct,
            "data.to_predict",
            group_id,
            bootstrap_servers,
            enable_auto_commit,
            backend_type,
            backend_config,
        )


class DataToPredictQueue(BaseQueueFacade[DataToPredictStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            DataToPredictStruct,
            "data.to_predict",
            lambda message: str(message.player_id % 10),
            group_id,
            bootstrap_servers,
            enable_auto_commit,
            backend_type,
            backend_config,
        )
