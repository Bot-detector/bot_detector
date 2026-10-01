"""Zero-wiring scenario: consume a fake kafka feed on the clock.

The simplest shape a scenario can have: pure asyncio code, no app, no
seams. It only needs the loop swap that dst.run performs.
"""

from pydantic import BaseModel, Field

from dst import IoConfig, MachineConfig, VirtualMachine
from dst.systems import FakeKafka, KafkaConfig


class KafkaSmokeConfig(BaseModel):
    duration_s: float = Field(default=10.0, gt=0.0)
    feed_rate_s: int = Field(default=100, gt=0)
    parse_cost_s: float = Field(default=0.0005, ge=0.0)


class KafkaSmokeReport(BaseModel):
    duration_s: float
    feed_rate_s: int
    parse_cost_s: float
    consumed: int
    produced: int
    backlog: int
    machine_cpu_calls: int
    machine_utilization: float


async def main(**kwargs) -> KafkaSmokeReport:
    """Consume a paced fake kafka feed for duration_s of virtual time."""
    config = KafkaSmokeConfig(**kwargs)
    machine = VirtualMachine(
        MachineConfig(io={"kafka": IoConfig(mean_ms=0.01, jitter_ms=0.005)})
    )
    kafka = FakeKafka(
        machine,
        KafkaConfig(rate_s=config.feed_rate_s, parse_cost_s=config.parse_cost_s),
    )
    await kafka.start()
    while machine.clock.time() < config.duration_s:
        await kafka.get_one()
    await kafka.stop()
    return KafkaSmokeReport(
        duration_s=machine.clock.time(),
        feed_rate_s=config.feed_rate_s,
        parse_cost_s=config.parse_cost_s,
        consumed=kafka.consumed_total,
        produced=kafka.produced_total,
        backlog=kafka.backlog,
        machine_cpu_calls=machine.cpu_calls,
        machine_utilization=machine.utilization(),
    )
