import time

import orjson
from aiokafka import AIOKafkaConsumer, TopicPartition
from bot_detector.kafka.core.consumer_interface import ConsumerInterface


class BaseConsumer(ConsumerInterface):
    def __init__(
        self,
        topic: str,
        group_id: str,
        bootstrap_servers: str,
        enable_auto_commit: bool = True,
    ):
        self.topic = topic
        self._consumer = AIOKafkaConsumer(
            topic,
            group_id=group_id,
            value_deserializer=lambda x: orjson.loads(x),
            auto_offset_reset="earliest",
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
        )

    async def start(self):
        await self._consumer.start()
        return self._consumer

    async def stop(self):
        await self._consumer.stop()

    async def get_consumer(self):
        return self._consumer

    def _validate_value(self, value) -> tuple[dict | None, str | None]:
        if not isinstance(value, dict):
            return None, "Message value is not a dict"
        return value, None

    async def _consume_one(self) -> tuple[dict | None, str | None]:
        msg = await self._consumer.getone()
        value, error = self._validate_value(value=msg.value)
        return value, error

    async def _buffer_records(self, max_records: int, timeout_ms: int) -> list:
        buffer = []
        start = time.time()

        while len(buffer) < max_records:
            time_left = timeout_ms / 1000 - (time.time() - start)

            if time_left <= 0:
                break

            records = await self._consumer.getmany(
                timeout_ms=int(time_left * 1000),
                max_records=max_records - len(buffer),
            )
            buffer.extend([msg.value for msgs in records.values() for msg in msgs])

        return buffer

    async def _consume_many(
        self,
        max_messages: int,
        timeout_ms: int,
    ) -> tuple[list[dict | None], list[str | None]]:
        msg_values = await self._buffer_records(
            max_records=max_messages,
            timeout_ms=timeout_ms,
        )

        values, errors = [], []

        for value, error in map(self._validate_value, msg_values):
            if error:
                errors.append(error)
            elif value is not None:
                values.append(value)
        return values, errors

    async def get_lag(self) -> int:
        total_lag = 0

        partitions = self._consumer.partitions_for_topic(self.topic)

        if partitions is None:
            return 0

        for partition in partitions:
            tp = TopicPartition(self.topic, partition)
            committed = await self._consumer.committed(tp)
            end_offset = await self._consumer.end_offsets([tp])
            lag = end_offset[tp] - committed
            total_lag += lag

        return total_lag

    async def commit(self):
        await self._consumer.commit()
