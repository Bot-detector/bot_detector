import asyncio

from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient
from bot_detector.event_queue.core.errors import LagProbeError
from bot_detector.event_queue.lag_probe.interface import LagProbeProtocol

# every external await in lag() is bounded by one overall timeout
PROBE_TIMEOUT_S = 30.0


class KafkaLagProbe(LagProbeProtocol):
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._consumer: AIOKafkaConsumer | None = None
        self._admin: AIOKafkaAdminClient | None = None

    async def start(self) -> None:
        consumer = AIOKafkaConsumer(
            bootstrap_servers=self.bootstrap_servers,
            enable_auto_commit=False,
        )
        admin = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)

        await admin.start()
        try:
            await consumer.start()
        except BaseException:
            # cleanup on cancel too; never swallow the original error
            await admin.stop()
            raise
        # assign only after both starts succeeded, so a failed start()
        # leaves None fields and the next start() actually retries
        self._consumer = consumer
        self._admin = admin

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()
        if self._admin:
            await self._admin.close()

    async def lag(self, topic: str, group_id: str) -> int:
        if self._consumer is None or self._admin is None:
            raise LagProbeError("LagProbe not started, call start() first")

        async with asyncio.timeout(PROBE_TIMEOUT_S):
            partitions = self._consumer.partitions_for_topic(topic)
            # None means metadata is unavailable (broker down, topic absent):
            # raising beats reporting lag=0, which reads as false-healthy
            if not partitions:
                raise LagProbeError(f"No partitions found for topic: {topic}")

            topic_partitions = [TopicPartition(topic, p) for p in partitions]

            # latest offsets
            end_offsets = await self._consumer.end_offsets(topic_partitions)
            first_offsets = await self._consumer.beginning_offsets(topic_partitions)

            # committed group offsets (no group join!)
            group_offsets = await self._admin.list_consumer_group_offsets(group_id)

            total_lag = 0

            for tp in topic_partitions:
                end_offset = end_offsets[tp]
                first_offset = first_offsets[tp]
                if end_offset < first_offset:
                    # This can happen if the topic was deleted and recreated, or if the partition was truncated.
                    # In this case, we consider all messages as consumed (lag = 0) to avoid negative lag.
                    continue
                committed = group_offsets.get(tp)
                committed_offset = committed.offset if committed else 0

                if committed_offset < first_offset:
                    # This can happen if the consumer group has never consumed from this partition, or if it has fallen behind and the partition has been truncated.
                    # In this case, we consider the lag to be the number of messages from the first offset to the end offset.
                    total_lag += max(end_offset - first_offset, 0)
                    continue
                total_lag += max(end_offset - committed_offset, 0)

            return total_lag
