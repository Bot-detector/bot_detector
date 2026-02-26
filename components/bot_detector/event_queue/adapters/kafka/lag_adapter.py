from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient
from bot_detector.event_queue.lag_probe.interface import LagProbeProtocol


class KafkaLagProbe(LagProbeProtocol):
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._consumer: AIOKafkaConsumer | None = None
        self._admin: AIOKafkaAdminClient | None = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            bootstrap_servers=self.bootstrap_servers,
            enable_auto_commit=False,
        )
        self._admin = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)

        await self._consumer.start()
        await self._admin.start()

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()
        if self._admin:
            await self._admin.close()

    async def lag(self, topic: str, group_id: str) -> int:
        assert self._consumer is not None, "Consumer not initialized."
        assert self._admin is not None, "Admin client not initialized."

        partitions = self._consumer.partitions_for_topic(topic)
        if not partitions:
            return 0

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
