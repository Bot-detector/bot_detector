from typing import Protocol, runtime_checkable


@runtime_checkable
class LagProbeProtocol(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def lag(self, topic: str, group_id: str) -> int: ...
