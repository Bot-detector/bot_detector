from aiokafka import AIOKafkaConsumer, TopicPartition

from bot_detector.event_queue.lag_probe.interface import LagProbeProtocol


class KafkaLagProbe(LagProbeProtocol):
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._consumers: dict[str, AIOKafkaConsumer] = {}

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        for consumer in self._consumers.values():
            await consumer.stop()
        self._consumers.clear()

    async def lag(self, topic: str, group_id: str) -> int:
        consumer = await self._get_or_create_consumer(topic=topic, group_id=group_id)

        partitions = consumer.partitions_for_topic(topic)
        if partitions is None:
            return 0

        total_lag = 0
        for partition in partitions:
            tp = TopicPartition(topic, partition)
            committed = await consumer.committed(tp) or 0
            end_offsets = await consumer.end_offsets([tp])
            total_lag += end_offsets[tp] - committed
        return total_lag

    async def _get_or_create_consumer(
        self,
        topic: str,
        group_id: str,
    ) -> AIOKafkaConsumer:
        if group_id in self._consumers:
            return self._consumers[group_id]

        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=False,
        )
        await consumer.start()
        self._consumers[group_id] = consumer
        return consumer
