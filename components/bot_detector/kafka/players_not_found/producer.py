from bot_detector.kafka.core.base_producer import BaseProducer
from .struct import NotFoundStruct


class PlayersNotFoundProducer(BaseProducer[NotFoundStruct]):
    def __init__(self, bootstrap_servers: str, max_async_actions: int = 10):
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            topic="players.not_found",
            max_async_actions=max_async_actions,
        )
