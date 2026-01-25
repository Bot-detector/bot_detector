from bot_detector.kafka.core.base_consumer import BaseConsumer

from .struct import ToScrapeStruct


class PlayersToScrapeConsumer(BaseConsumer[ToScrapeStruct]):
    """
    Typed consumer for the 'players.to_scrape' topic.
    Automatically validates messages into ToScrapeStruct.
    """

    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str,
        enable_auto_commit: bool = True,
    ):
        super().__init__(
            topic="players.to_scrape",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            deserializer=ToScrapeStruct.model_validate,
            enable_auto_commit=enable_auto_commit,
        )
