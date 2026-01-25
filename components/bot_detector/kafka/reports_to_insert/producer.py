from bot_detector.kafka.core.base_producer import BaseProducer
from .struct import ReportsToInsertStruct


class ReportsToInsertProducer(BaseProducer[ReportsToInsertStruct]):
    def __init__(self, bootstrap_servers: str, max_async_actions: int = 10):
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            topic="reports.to_insert",
            max_async_actions=max_async_actions,
        )
