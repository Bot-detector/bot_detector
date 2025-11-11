from bot_detector.kafka.core.base_producer import BaseProducer

from .struct import DataToPredictStruct


class DataToPredictProducer(BaseProducer):
    def __init__(self, bootstrap_servers: str):
        super().__init__(bootstrap_servers, topic="data.to_predict")

    # inherited
    async def start(self):
        await super().start()

    async def stop(self):
        await super().stop()

    async def get_producer(self):
        return await super().get_producer()

    async def produce_one(
        self,
        data: DataToPredictStruct,
        partition_key: str | None = None,
    ):
        if not isinstance(data, DataToPredictStruct):
            raise Exception()

        partition_key = str(int(data.player_id) % 10)

        await super().produce_one(
            data=data.model_dump(),
            topic=None,
            partition_key=partition_key,
        )
