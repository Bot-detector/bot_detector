from bot_detector.kafka.core.base_producer import BaseProducer

from .struct import DataToPredictStruct


class DataToPredictProducer(BaseProducer[DataToPredictStruct]):
    """
    Typed producer for the 'data.to_predict' topic.
    Automatically serializes DataToPredictStruct messages.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        max_async_actions: int = 10,
    ):
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            topic="data.to_predict",
            max_async_actions=max_async_actions,
        )

    async def produce_one(
        self,
        message: DataToPredictStruct,
        topic: str | None = None,
        partition_key: bytes | None = None,
        max_retries: int = 5,
    ):
        """
        Produce a single DataToPredictStruct message.
        """
        await super().produce_one(
            message, topic=topic, partition_key=partition_key, max_retries=max_retries
        )
