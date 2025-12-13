import logging

from bot_detector.kafka.core.base_consumer import BaseConsumer

from .struct import DataToPredictStruct

logger = logging.getLogger(__name__)


class DataToPredictConsumer(BaseConsumer):
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
            enable_auto_commit=enable_auto_commit,
        )

    # inherited methods:
    async def start(self):
        return await super().start()

    async def stop(self):
        return await super().stop()

    async def get_consumer(self):
        return await super().get_consumer()

    async def _consume_one(self) -> tuple[dict | None, str | None]:
        return await super()._consume_one()

    async def _buffer_records(self, max_records: int, timeout_ms: int) -> list:
        return await super()._buffer_records(max_records, timeout_ms)

    async def _consume_many(
        self, max_messages: int, timeout_ms: int
    ) -> tuple[list[dict | None], list[str | None]]:
        return await super()._consume_many(max_messages, timeout_ms)

    async def get_lag(self) -> int:
        return await super().get_lag()

    async def commit(self):
        return await super().commit()

    async def consume_one(self) -> DataToPredictStruct | None:
        value, error = await super()._consume_one()

        if error:
            return None

        if value is None:
            return None

        return DataToPredictStruct.model_validate(value)

    async def consume_many(
        self, max_messages: int, timeout_ms: int
    ) -> list[DataToPredictStruct]:
        values, errors = await super()._consume_many(max_messages, timeout_ms)
        for error in errors:
            if error is not None:
                logger.warning(f"Error while consuming many: {error}")
        return [DataToPredictStruct.model_validate(v) for v in values if v is not None]
