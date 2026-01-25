from bot_detector.kafka.core.base_producer import BaseProducer

from .struct import ToScrapeStruct


class PlayersToScrapeProducer(BaseProducer[ToScrapeStruct]):
    """
    Typed producer for the 'players.to_scrape' topic.
    Automatically serializes ToScrapeStruct messages.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        max_async_actions: int = 10,
    ):
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            topic="players.to_scrape",
            max_async_actions=max_async_actions,
        )
