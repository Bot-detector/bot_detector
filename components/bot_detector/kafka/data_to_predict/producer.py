from typing import Optional

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
        self, data: DataToPredictStruct, partition_key: Optional[bytes] = None
    ):
        """
        Produce a single DataToPredictStruct message.

        Automatically generates a partition key if not provided.
        """
        if partition_key is None:
            partition_key = str(int(data.player_id) % 10).encode("utf-8")

        await super().produce_one(data, partition_key=partition_key)
