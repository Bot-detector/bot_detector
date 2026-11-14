from dataclasses import dataclass

import orjson
from bot_detector.event_queue.adapters.kafka import (
    AIOKafkaConsumerAdapter,
    KafkaConfig,
    KafkaConsumerConfig,
)
from bot_detector.event_queue.adapters.kafka.adapter import _deserialize_value
from dst.testing import Invariant, Scorecard, Subscores, hard_gate
from prometheus_client import REGISTRY
from pydantic import BaseModel, ConfigDict, Field

PAGE_PARTITION = 0


class ScenarioConfig(BaseModel):
    """Knobs for the poison-advance scenario; small runs for tests."""

    model_config = ConfigDict(frozen=True)

    pages: int = Field(default=50, gt=0)
    page_size: int = Field(default=40, gt=0)
    batch: int = Field(default=25, gt=1)
    consume_timeout_ms: int = Field(default=50, gt=0)
    # every 7th record is unparseable bytes, every 11th is valid JSON with
    # a drifted schema; both must be skipped, never stall the consumer
    seed: int = 0


class PageMessage(BaseModel):
    player_id: int
    score: int


@dataclass(frozen=True, slots=True)
class _Record:
    """ConsumerRecord stand-in; the adapter only reads .value."""

    value: object


class _StubConsumer:
    """Serves pre-built pages of raw bytes, deserializing like aiokafka."""

    def __init__(self, pages: list[list[bytes]]):
        self._pages = pages
        self.calls = 0

    async def getmany(self, timeout_ms: int, max_records: int):
        self.calls += 1
        index = self.calls - 1
        if index >= len(self._pages):
            return {}
        page = self._pages[index]
        return {PAGE_PARTITION: [_Record(_deserialize_value(raw)) for raw in page]}

    async def commit(self):
        return None


def _record_bytes(index: int) -> bytes:
    if index % 7 == 0:
        return b"\xff not-json{{{ poison bytes"
    if index % 11 == 0:
        return orjson.dumps({"drift": True, "unknown_shape": [1, 2]})
    return orjson.dumps({"player_id": index, "score": index % 100})


def _build_pages(config: ScenarioConfig) -> list[list[bytes]]:
    total = config.pages * config.page_size
    return [
        [_record_bytes(i) for i in range(page, min(page + config.page_size, total))]
        for page in range(0, total, config.page_size)
    ]


async def main(**kwargs) -> Scorecard:
    """Run the commit-after-dequeue consume loop over poison-laced pages.

    The consumer uses the real adapter get_many/commit path (the loop the
    worker bases run). Before the skip fix, the first poison record aborted
    the batch, nothing committed, and the same page was re-fetched forever:
    an unbounded get_many call count with zero progress. Invariants:

    - ``advances_past_poison``: get_many calls stay within pages + slack
    - ``no_valid_loss``: every valid record is consumed exactly once
    - ``no_error_results``: get_many never returns an error value
    - ``skipped_matches_expected``: skip counter equals the poison total

    ``score`` = 0.0 if any invariant failed, else the mean subscores.
    Payloads are built from index arithmetic (no RNG), so runs replay
    byte-identically.
    """
    config = ScenarioConfig(**kwargs)
    pages = _build_pages(config)
    total = config.pages * config.page_size
    expected_poison = sum(1 for i in range(total) if i % 7 == 0 or i % 11 == 0)
    valid_total = total - expected_poison

    adapter = AIOKafkaConsumerAdapter(
        PageMessage,
        KafkaConfig(
            topic="poison_advance",
            bootstrap_servers="localhost:9092",
            consumer=True,
            producer=False,
            consumer_config=KafkaConsumerConfig(
                group_id="poison_advance",
                consume_timeout_ms=config.consume_timeout_ms,
            ),
            producer_config=None,
        ),
    )
    stub = _StubConsumer(pages)
    adapter.consumer = stub  # inject the transport boundary

    skipped_before = REGISTRY.get_sample_value("event_queue_messages_skipped_total")
    consumed = 0
    error_results = 0
    commits = 0
    rounds = 0
    max_rounds = config.pages + 10

    while consumed < valid_total:
        rounds += 1
        assert rounds <= max_rounds, (
            f"consume loop stalled: rounds={rounds} consumed={consumed}"
        )
        batch = await adapter.get_many(config.batch)
        if isinstance(batch, Exception):
            error_results += 1
            continue
        consumed += len(batch)
        commit_error = await adapter.commit()
        assert commit_error is None, f"commit failed: {commit_error}"
        commits += 1

    skipped = REGISTRY.get_sample_value("event_queue_messages_skipped_total") or 0
    skipped_delta = skipped - (skipped_before or 0)
    call_budget = config.pages + 3

    # subscore mapping onto the MVP-slim set (scenario-defined semantics):
    # loss   = valid records lost
    # keep_up = consumer progresses (calls within budget) instead of
    #           spinning forever on the same poison page
    # drain  = the poison workload drains fully: skipped == expected
    loss = 1.0 if consumed == valid_total else 0.0
    keep_up = 1.0 if stub.calls <= call_budget else 0.0
    drain = 1.0 if skipped_delta == expected_poison else 0.0

    card = Scorecard(
        seed=config.seed,
        counters={
            "consumed": consumed,
            "valid_total": valid_total,
            "skipped": int(skipped_delta),
            "expected_poison": expected_poison,
            "get_many_calls": stub.calls,
            "commits": commits,
            "error_results": error_results,
        },
        invariants=[
            Invariant(
                name="advances_past_poison",
                ok=stub.calls <= call_budget,
                detail=f"calls={stub.calls} budget={call_budget}",
            ),
            Invariant(
                name="no_valid_loss",
                ok=consumed == valid_total,
                detail=f"consumed={consumed} valid_total={valid_total}",
            ),
            Invariant(
                name="no_error_results",
                ok=error_results == 0,
                detail=f"error_results={error_results}",
            ),
            Invariant(
                name="skipped_matches_expected",
                ok=skipped_delta == expected_poison,
                detail=f"skipped={skipped_delta} expected={expected_poison}",
            ),
        ],
        subscores=Subscores(loss=loss, keep_up=keep_up, drain=drain),
        score=(loss + keep_up + drain) / 3.0,
    )
    card.score = hard_gate(card)
    return card
