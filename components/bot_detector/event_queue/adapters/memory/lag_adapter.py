from bot_detector.event_queue.lag_probe.interface import LagProbeProtocol


class MemoryLagProbe(LagProbeProtocol):
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def lag(self, topic: str, group_id: str) -> int:
        return 0
