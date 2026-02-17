from bot_detector.event_queue.adapters.kafka import KafkaConfig
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.structs import ReportsToInsertStruct

from .base import BackendType, BaseConsumerFacade, BaseProducerFacade, BaseQueueFacade


class ReportsToInsertProducer(BaseProducerFacade[ReportsToInsertStruct]):
    def __init__(
        self,
        bootstrap_servers: str | None,
        max_async_actions: int = 10,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        _ = max_async_actions
        super().__init__(
            ReportsToInsertStruct,
            "reports.to_insert",
            lambda message: str(message.report.reported_ts),
            bootstrap_servers,
            backend_type,
            backend_config,
        )


class ReportsToInsertConsumer(BaseConsumerFacade[ReportsToInsertStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            ReportsToInsertStruct,
            "reports.to_insert",
            group_id,
            bootstrap_servers,
            enable_auto_commit,
            backend_type,
            backend_config,
        )


class ReportsToInsertQueue(BaseQueueFacade[ReportsToInsertStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            ReportsToInsertStruct,
            "reports.to_insert",
            lambda message: str(message.report.reported_ts),
            group_id,
            bootstrap_servers,
            enable_auto_commit,
            backend_type,
            backend_config,
        )
