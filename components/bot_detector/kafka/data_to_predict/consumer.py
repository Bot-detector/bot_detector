import logging

from bot_detector.kafka.core.base_consumer import BaseConsumer

from .struct import DataToPredictStruct

logger = logging.getLogger(__name__)


class DataToPredictConsumer(BaseConsumer[DataToPredictStruct]):
    """
    Typed consumer for the 'data.to_predict' topic.
    Automatically validates messages into DataToPredictStruct.
    """

    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str,
        enable_auto_commit: bool = True,
    ):
        super().__init__(
            topic="data.to_predict",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            deserializer=DataToPredictStruct.model_validate,
            enable_auto_commit=enable_auto_commit,
        )

    # --- Optionally override consume_many to log errors ---
    async def consume_many(
        self, max_messages: int, timeout_ms: int
    ) -> list[DataToPredictStruct]:
        values, errors = await super().consume_many(max_messages, timeout_ms)
        logger.error(f"Consumed {len(values)} messages with {len(errors)} errors")
        return [v for v in values if v is not None]
