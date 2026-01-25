from bot_detector.kafka.core.base_consumer import BaseConsumer
from .struct import NotFoundStruct


class PlayersNotFoundConsumer(BaseConsumer[NotFoundStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str,
        enable_auto_commit: bool = True,
    ):
        super().__init__(
            topic="players.not_found",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            deserializer=NotFoundStruct.model_validate,
            enable_auto_commit=enable_auto_commit,
        )
