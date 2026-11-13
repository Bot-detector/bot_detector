from pydantic import BaseModel, Field

from dst.loop import running_clock
from dst.systems import KafkaConfig, SimFeedKafka


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
    # parse-cost counters read off SimFeedKafka.cpu; machine_* names
    # kept for report consumers
    machine_cpu_calls: int
    machine_utilization: float


async def main(**kwargs) -> KafkaSmokeReport:
    """Consume a paced kafka feed for duration_s of virtual time.

    The simplest shape a scenario can have: pure asyncio, no app, no
    seams — only the loop swap dst.run performs.
    """
    config = KafkaSmokeConfig(**kwargs)
    clock = running_clock()
    kafka = SimFeedKafka(
        KafkaConfig(feed_rate_s=config.feed_rate_s, parse_cost_s=config.parse_cost_s)
    )
    await kafka.start()
    while clock.time() < config.duration_s:
        await kafka.get_one()
    await kafka.stop()
    elapsed_s = clock.time()
    utilization = kafka.cpu.busy_s / elapsed_s if elapsed_s > 0.0 else 0.0
    assert utilization >= 0.0, f"negative utilization: {utilization!r}"
    return KafkaSmokeReport(
        duration_s=elapsed_s,
        feed_rate_s=config.feed_rate_s,
        parse_cost_s=config.parse_cost_s,
        consumed=kafka.consumed_total,
        produced=kafka.produced_total,
        backlog=kafka.backlog,
        machine_cpu_calls=kafka.cpu.calls,
        machine_utilization=min(1.0, utilization),
    )
