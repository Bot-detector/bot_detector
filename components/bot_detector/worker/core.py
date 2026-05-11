from bot_detector.event_queue.adapters.kafka import KafkaConfig
from bot_detector.event_queue.core import QueueBackendProtocol as Queue
from bot_detector.event_queue.factory import QueueFactory


class Worker:
    def __init__(self, config: KafkaConfig, model: T):
        self.queue = self._get_queue(config, model)

    @staticmethod
    def _get_queue(config: KafkaConfig, model: T) -> Queue:
        queue = QueueFactory.create_queue(
            model=model,
            queue_type="queue",
            backend_type="kafka",
            config=config,
        )
        assert isinstance(queue, Queue)
        return queue

    def handle(self):
        # Implement the logic to run the worker
        pass
