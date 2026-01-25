from bot_detector.kafka.core.base_consumer import BaseConsumer
from .struct import ReportsToInsertStruct


class ReportsToInsertConsumer(BaseConsumer[ReportsToInsertStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str,
        enable_auto_commit: bool = True,
    ):
        super().__init__(
            topic="reports.to_insert",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            deserializer=ReportsToInsertStruct.model_validate,
            enable_auto_commit=enable_auto_commit,
        )
