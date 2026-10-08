"""kafka_drain_1m (spec lane F1): feed 1M messages into one SimBroker
partition at a paced virtual rate while a consumer drains it in bulk
batches on the same loop.

Measures whether the consumer keeps up with the feed and how long the
backlog takes to empty after the feed ends (spec sections 6, 6.2,
MVP-slim subscores):

- ``keep_up`` = consumed rate / feed rate, capped at 1.0
- ``drain``   = 1.0 when ``drain_end - feed_end <= drain_budget_s``,
  else linear down to 0.0 at 4x the budget
- ``loss``    = 1.0 when zero messages were lost, else 0.0

``score`` = 0.0 if any invariant failed, else the mean of the three
subscores (hard gate, spec section 6.2). No faults by default: this
run is the drain/keep-up skeleton; fault knobs arrive with later
tasks. Timestamps come from the loop clock, which under ``dst.run``
is the virtual clock.
"""

import asyncio

from pydantic import BaseModel, ConfigDict, Field

from dst import KafkaFaultConfig
from dst.systems import SimBroker, SimBrokerConfig
from dst.testing import Invariant, Scorecard, Subscores, hard_gate

TOPIC = "drain"
PARTITION = 0
GROUP = "drain_1m"


class ScenarioConfig(BaseModel):
    """Knobs for the drain scenario; small runs for tests."""

    model_config = ConfigDict(frozen=True)

    total: int = Field(default=1_000_000, gt=0)
    rate_s: int = Field(default=100_000, gt=0)
    batch: int = Field(default=10_000, gt=0)
    drain_budget_s: float = Field(default=30.0, gt=0.0)
    seed: int = 0
    payload_bytes: int = Field(default=64, ge=1)
    consumer_batch: int = Field(default=0, ge=0)  # 0 = same as batch
    consumer_sleep_s: float = Field(default=0.0, ge=0.0)


async def main(**kwargs) -> Scorecard:
    """Feed ``total`` messages at ``rate_s`` while a consumer drains."""
    config = ScenarioConfig(**kwargs)
    broker = SimBroker(
        SimBrokerConfig(
            seed=config.seed,
            faults=KafkaFaultConfig(),
            payload_bytes=config.payload_bytes,
        )
    )
    loop = asyncio.get_running_loop()
    tick_s = config.batch / config.rate_s
    fetch_count = config.consumer_batch or config.batch
    idle_s = min(tick_s, 0.01)

    faulted_produce = 0
    faulted_fetch = 0
    consumed = 0
    expected_offset = 0
    offsets_monotonic = True
    feed_start = 0.0
    feed_end = 0.0
    drain_end = 0.0

    async def produce_paced() -> None:
        nonlocal faulted_produce, feed_start, feed_end
        remaining = config.total
        feed_start = loop.time()
        while remaining > 0:
            count = min(config.batch, remaining)
            await asyncio.sleep(tick_s)
            error = await broker.produce(TOPIC, PARTITION, count)
            if error is not None:
                faulted_produce += 1
            remaining -= count
        feed_end = loop.time()

    async def drain_bulk() -> None:
        nonlocal faulted_fetch, consumed, expected_offset, offsets_monotonic
        nonlocal drain_end
        while consumed < config.total:
            messages = await broker.get_many(TOPIC, PARTITION, GROUP, fetch_count)
            if not messages:
                await asyncio.sleep(idle_s)
                continue
            for message in messages:
                if isinstance(message, Exception):
                    faulted_fetch += 1
                    continue
                if message.offset != expected_offset:
                    offsets_monotonic = False
                expected_offset = message.offset + 1
                consumed += 1
            if config.consumer_sleep_s > 0.0:
                await asyncio.sleep(config.consumer_sleep_s)
        drain_end = loop.time()

    await asyncio.gather(produce_paced(), drain_bulk())

    produced = broker.produced_total
    feed_span = max(feed_end - feed_start, 1e-9)
    consume_span = max(drain_end - feed_start, 1e-9)
    feed_rate = produced / feed_span
    consume_rate = consumed / consume_span
    ratio = consume_rate / feed_rate if feed_rate > 0 else 1.0
    keep_up = 1.0 if ratio >= 1.0 - 1e-9 else min(1.0, ratio)

    gap = max(0.0, drain_end - feed_end)
    budget = config.drain_budget_s
    if gap <= budget:
        drain = 1.0
    else:
        drain = max(0.0, 1.0 - (gap - budget) / (3.0 * budget))

    lost = produced - consumed
    loss = 1.0 if lost == 0 else 0.0

    card = Scorecard(
        seed=config.seed,
        counters={
            "produced": produced,
            "consumed": consumed,
            "faulted_produce": faulted_produce,
            "faulted_fetch": faulted_fetch,
        },
        invariants=[
            Invariant(
                name="no_loss",
                ok=consumed == produced,
                detail=f"lost={lost}",
            ),
            Invariant(
                name="drained",
                ok=broker.lag(TOPIC, PARTITION, GROUP) == 0,
                detail=f"lag={broker.lag(TOPIC, PARTITION, GROUP)}",
            ),
            Invariant(
                name="offsets_monotonic",
                ok=offsets_monotonic and expected_offset == consumed,
                detail=f"next_offset={expected_offset} consumed={consumed}",
            ),
        ],
        subscores=Subscores(loss=loss, keep_up=keep_up, drain=drain),
        score=(keep_up + drain + loss) / 3.0,
    )
    card.score = hard_gate(card)
    return card
