from bot_detector.kafka.core.base_producer import BaseProducer
from .struct import ScrapedStruct


class PlayersScrapedProducer(BaseProducer[ScrapedStruct]):
    def __init__(self, bootstrap_servers: str, max_async_actions: int = 10):
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            topic="players.scraped",
            max_async_actions=max_async_actions,
        )
