"""The real hiscore scraper pipeline on the DST virtual clock.

The scraper runs as three stages wired by bounded asyncio queues:
consume -> task_queue -> fetch pool -> results_queue -> processors.
The real stage functions from `bot_detector.hiscore_scraper` run
unmodified: `consumer.consume` (batched get_many + one commit per
batch), the fetch loop `fetcher.fetch` (per-proxy RateLimiter windows
of 20/s + 1200/min, RetryTracker backoff, sticky proxy assignment) and
`processor.process` (transform + kafka produce). Only the I/O seams are
replaced:

- kafka: a SimKafka broker per topic with `partitions` (prod: 4)
  fed at `feed_rate_s` names per virtual second, packed
  `names_per_message` names per kafka message. One consumer task pulls
  `consume_batch_size` names per get_many; the commit models the real
  per-batch commit as a single broker RTT that clears every fetched
  message at once. Broker RTTs ride the machine's Network model
  (latency, jitter, `kafka_bandwidth_mbps` transfer time, packet loss,
  partition) through a `kafka_connection_limit` connection pool
  (0 = unlimited).
- jagex: SimHiscoreAPI draws per-fetch outcomes on a seeded RNG:
  success (~success_latency_s), not_found (slow, ~not_found_latency_s,
  the 404 path) and transient errors (requeue + retry backoff).
- proxies: an in-memory manager with `proxies` proxies; fetchers are
  assigned sticky by index modulo the pool size, so each proxy's rate
  windows are shared by fetchers/proxies fetchers.

The scenario answers "where is the pipeline slow" with two lenses:
stage-time shares (where pipeline time goes) and the binding cap among
feed, consumer serial path, fetch pool (Little's law: fetchers / mean
fetch latency) and the per-proxy rate ceilings (proxies x 20/s).

Latency calibration (prod, Nov 2026): overall fetch p50 ~ 1.7s,
p99 ~ 5s, and not_found runs ~20% ahead of found (share 1.2/2.2
~ 54.5%). Because not_found is the majority outcome, the mixture
median sits inside its distribution: not_found is drawn lognormal
with median 1.7s and p99 5s, successes stay tight around 1.0s
(uniform jitter), which together reproduce the observed fleet
signatures (~450/s sprint, ~300/s crawl) and the mixture p50/p99.
"""

import asyncio
import logging
import math
import os
import random
from collections import deque
from collections.abc import Callable, Coroutine
from contextlib import nullcontext
from datetime import datetime
from typing import Any

os.environ.setdefault("PROXY_API_KEY", "sim")  # ProxySettings is required-env

import orjson  # noqa: E402
from bot_detector.event_queue.core import (  # noqa: E402
    Queue,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
    QueueProducer,
)
from bot_detector.event_queue.structs import (  # noqa: E402
    NotFoundStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.hiscore_scraper import consumer as scraper_consumer  # noqa: E402
from bot_detector.hiscore_scraper import fetcher as scraper_fetcher  # noqa: E402
from bot_detector.hiscore_scraper import processor as scraper_processor  # noqa: E402
from bot_detector.hiscore_scraper.fetcher import ProxyRuntime  # noqa: E402
from bot_detector.hiscore_scraper.structs import FetchResult  # noqa: E402
from bot_detector.osrs_hs_api.exceptions import (  # noqa: E402
    Err,
    Ok,
    PlayerDoesNotExist,
)
from bot_detector.osrs_hs_api.structs import (  # noqa: E402
    Activity,
    PlayerStats,
    Skill,
)
from bot_detector.proxy_manager import Settings as ProxySettings  # noqa: E402
from bot_detector.rate_limiter import RateLimiter, Window  # noqa: E402
from bot_detector.structs import MetaData, PlayerStruct  # noqa: E402
from pydantic import BaseModel, Field, ValidationError, model_validator  # noqa: E402

from dst import Machine, MachineConfig, NetworkConfig, virtual_time  # noqa: E402

logger = logging.getLogger(__name__)

TICK_S = 0.01  # feed pacing granularity, matches dst.systems.fake_kafka
Z_99 = 2.3263478740408408  # standard-normal z-score at p99


def _pct(sorted_samples: list[float], q: float) -> float:
    """q-quantile of an ascending list (nearest-rank)."""
    if not sorted_samples:
        return 0.0
    idx = min(int(q * len(sorted_samples)), len(sorted_samples) - 1)
    return sorted_samples[idx]


class ScraperThroughputConfig(BaseModel):
    """One simulated pipeline run: feed shape, broker costs, jagex mix."""

    duration_s: float = Field(default=120.0, gt=0.0)
    fetchers: int = Field(default=1800, ge=1)
    processors: int = Field(default=16, ge=1)
    proxies: int = Field(default=250, ge=1)
    consume_batch_size: int = Field(default=200, ge=1)
    task_queue_maxsize: int = Field(default=2000, ge=1)
    results_queue_maxsize: int = Field(default=2000, ge=1)
    pool_size: int = Field(default=2_000, ge=1)
    feed_rate_s: int = Field(default=2_000, gt=0)
    partitions: int = Field(default=4, ge=1)
    seed: int = 42
    machine_seed: int = 7
    # simulated broker costs, virtual seconds per message/call
    fetch_cost_s: float = Field(default=0.002, ge=0.0)
    parse_cost_s: float = Field(default=0.0002, ge=0.0)
    commit_cost_s: float = Field(default=0.005, ge=0.0)
    produce_cost_s: float = Field(default=0.002, ge=0.0)
    serialize_cost_s: float = Field(default=0.0001, ge=0.0)
    max_buffer: int = Field(default=60_000, gt=0)
    # names packed per kafka message (prod idea: batches of 10). One
    # fetch RTT + one commit per message; parse stays per name.
    names_per_message: int = Field(default=1, ge=1)
    # simulated broker network link: 0 connections = unlimited pool;
    # 1 serializes the consumer's fetch and commit round trips on a
    # single connection. RTTs ride the machine's Network model, so
    # scenario NetworkConfig (mean/jitter/bandwidth/packet loss) and
    # machine.network.partition() apply to broker traffic as well.
    kafka_connection_limit: int = Field(default=0, ge=0)
    kafka_payload_bytes: int = Field(default=512, ge=1)
    # broker link bandwidth: 800 Mbps = 100 MB/s (prod-plausible LAN link).
    # Transfer time per message = bytes * 8 / bandwidth, on top of the
    # explicit RTT costs.
    kafka_bandwidth_mbps: float = Field(default=800.0, gt=0.0)
    # drop null fields (ironman/hardcore_ironman/ultimate_ironman/
    # normalized_name) from serialized messages to shrink them
    exclude_none_fields: bool = False
    # simulated jagex fetch outcomes; prod calibration (Nov 2026):
    # overall fetch p50 ~1.7s (the not_found median - it is the majority
    # outcome), p99 ~5s, not_found share 1.2/2.2 ~ 54.5%
    success_latency_s: float = Field(default=1.0, ge=0.0)
    not_found_latency_s: float = Field(default=1.7, ge=0.0)
    not_found_pct: float = Field(default=54.5, ge=0.0, le=100.0)
    latency_p99_over_p50: float = Field(default=2.9412, gt=1.0)
    error_pct: float = Field(default=2.0, ge=0.0, le=100.0)
    error_latency_s: float = Field(default=1.0, ge=0.0)
    latency_jitter: float = Field(default=0.25, ge=0.0)

    @model_validator(mode="after")
    def check_outcome_mix(self):
        if self.not_found_pct + self.error_pct > 100.0:
            raise ValueError(
                f"not_found_pct + error_pct must be <= 100, got "
                f"{self.not_found_pct} + {self.error_pct}"
            )
        return self


class StageStat(BaseModel):
    """One worker-loop stage: call count, virtual time, blocked time."""

    calls: int = 0
    total_s: float = 0.0
    blocked_s: float = 0.0  # waiting on shared state (feed, commit lock)
    share_pct: float = 0.0


class OutcomeCounts(BaseModel):
    scraped: int = 0
    not_found: int = 0
    errors: int = 0
    requeues: int = 0


class FetchLatencyStat(BaseModel):
    """Distribution summary of one fetch outcome's latency samples."""

    calls: int = 0
    mean_s: float = 0.0
    p50_s: float = 0.0
    p99_s: float = 0.0


class ScraperThroughputReport(BaseModel):
    """End state of one run plus the slowness lenses."""

    config: ScraperThroughputConfig
    duration_s: float
    fetchers: int
    processors: int
    proxies: int
    partitions: int
    feed_produced: int
    requeues: int
    consumed: int
    messages_consumed: int
    backlog: int
    per_partition_produced: list[int]
    per_partition_consumed: list[int]
    scraped_produced: int
    not_found_produced: int
    outcomes: OutcomeCounts
    latency: dict[str, FetchLatencyStat]
    commits: int
    avg_name_bytes: float
    bytes_transferred: int
    kafka_fetch_failures: int
    kafka_commit_failures: int
    throughput_s: float
    fleet_cap_s: float
    consumer_cap_s: float
    consumer_serial_s: float
    rate_cap_s: float
    binding: str
    mean_iteration_s: float
    busy_stage_s: float
    stages: dict[str, StageStat]

    def summary(self) -> str:
        """Human-readable slowness breakdown for logs and test output."""
        link_note = (
            "single connection serializes fetch+commit RTTs"
            if self.config.kafka_connection_limit == 1
            else "fetch RTT and parse CPU run concurrently"
        )
        lines = [
            f"throughput {self.throughput_s:.1f}/s over {self.duration_s:.0f}s "
            f"({self.fetchers} fetchers, {self.processors} processors, "
            f"{self.proxies} proxies, {self.partitions} partitions, "
            f"consumed {self.consumed} names in {self.messages_consumed} "
            f"messages, backlog {self.backlog})",
            f"caps/s: binding={self.binding} consumer={self.consumer_cap_s:.1f} "
            f"fleet={self.fleet_cap_s:.1f} rate={self.rate_cap_s:.1f} "
            f"feed={self.config.feed_rate_s}",
            (
                f"consumer serial path: commit RTT "
                f"{self.config.commit_cost_s * 1000:.2f}ms per batch of "
                f"{self.config.consume_batch_size} "
                f"({self.consumer_serial_s * 1000:.3f}ms/player; {link_note})"
            ),
            (
                f"broker link: {self.config.kafka_bandwidth_mbps:.0f} Mbps, "
                f"avg name {self.avg_name_bytes:.0f}B, "
                f"transferred {self.bytes_transferred / 1e6:.1f}MB, "
                f"fetch failures {self.kafka_fetch_failures}"
            ),
            f"mean iteration {self.mean_iteration_s:.3f}s",
            "stage-time shares:",
        ]
        for name, stage in sorted(self.stages.items(), key=lambda kv: -kv[1].total_s):
            blocked = (
                f" (blocked {stage.blocked_s:.1f}s)" if stage.blocked_s > 0 else ""
            )
            lines.append(
                f"  {name:<14} {stage.share_pct:5.1f}%  "
                f"{stage.total_s:8.1f}s in {stage.calls} calls{blocked}"
            )
        lines.append("fetch latency by outcome:")
        for outcome in ("success", "not_found", "error"):
            stat = self.latency.get(outcome)
            if stat is not None and stat.calls > 0:
                lines.append(
                    f"  {outcome:<9} p50 {stat.p50_s:5.2f}s  "
                    f"p99 {stat.p99_s:5.2f}s  mean {stat.mean_s:5.2f}s  "
                    f"n={stat.calls}"
                )
        return "\n".join(lines)


class Stage:
    """Mutable accumulator for one stage; converted to StageStat later."""

    def __init__(self) -> None:
        self.calls = 0
        self.total_s = 0.0
        self.blocked_s = 0.0

    def add(self, dt_s: float, blocked_s: float = 0.0) -> None:
        self.calls += 1
        self.total_s += dt_s
        self.blocked_s += blocked_s


class RunState:
    """Per-run accounting shared by the broker, fakes and patches."""

    def __init__(self, machine: Machine) -> None:
        self.clock = machine.clock
        self.stages: dict[str, Stage] = {
            name: Stage()
            for name in (
                "proxy_get",
                "kafka_get",
                "commit",
                "rate_limit",
                "fetch",
                "transform",
                "produce",
            )
        }
        self.outcomes = OutcomeCounts()
        self.fetch_samples: dict[str, list[float]] = {
            "success": [],
            "not_found": [],
            "error": [],
        }

    def now(self) -> float:
        return self.clock.time()

    def stage(self, name: str) -> Stage:
        return self.stages[name]


def _jittered(rng: random.Random, mean_s: float, jitter: float) -> float:
    return mean_s * rng.uniform(1.0 - jitter, 1.0 + jitter)


class SimKafka:
    """One simulated topic: paced multi-partition feed + consumer path.

    The consumer surface mirrors what the real adapter does per message:
    a blocked wait for data (all workers park here when the consumer is
    the bottleneck), a fetch round trip, then real orjson + pydantic
    parsing charged to the machine's serial core. commit() is a broker
    RTT under a single-flight lock: one consumer instance serializes
    every worker's per-message commit, exactly the real adapter's shape.
    """

    def __init__(
        self,
        machine: Machine,
        config: ScraperThroughputConfig,
        state: RunState,
        *,
        feed: bool,
    ):
        self.machine = machine
        self.config = config
        self.state = state
        self.feed = feed
        self._delivery: asyncio.Queue[tuple[int, int, list[bytes]]] = asyncio.Queue(
            maxsize=config.max_buffer
        )
        self._pending: deque[bytes] = deque()  # names left in the fetched batch
        self._uncommitted = 0  # fetched messages awaiting their one commit
        self._commit_lock = asyncio.Lock()
        limit = config.kafka_connection_limit
        self._connections: asyncio.Semaphore | None = (
            asyncio.Semaphore(limit) if limit > 0 else None
        )
        self._pacer: asyncio.Task[None] | None = None
        self._pool = build_payload_pool(config.pool_size, config.exclude_none_fields)
        self.avg_name_bytes = sum(len(p) for p in self._pool) / len(self._pool)
        self._pool_cursor = 0
        self._out_batch: list[bytes] = []
        self._round_robin = 0
        self._batch_offset = 0
        self.feed_produced = 0
        self.produced_total = 0
        self.requeues = 0
        self.consumed = 0
        self.messages_consumed = 0
        self.commits = 0
        self.bytes_transferred = 0
        self.fetch_failures = 0
        self.commit_failures = 0
        self.produced_per_partition = [0] * config.partitions
        self.consumed_per_partition = [0] * config.partitions

    @property
    def backlog(self) -> int:
        """Unconsumed to_scrape records: feed + requeues - consumed."""
        return self.feed_produced + self.requeues - self.consumed

    def _partition(self, key: str | None) -> int:
        if key is not None:
            return int(key) % self.config.partitions
        partition = self._round_robin % self.config.partitions
        self._round_robin += 1
        return partition

    async def start_feed(self) -> None:
        if self.feed and self._pacer is None:
            self._pacer = asyncio.create_task(self._pace(), name="sim-feed-pacer")

    async def stop_feed(self) -> None:
        if self._pacer is not None:
            self._pacer.cancel()
            try:
                await self._pacer
            except asyncio.CancelledError:
                pass
            self._pacer = None

    async def _pace(self) -> None:
        """Pack names into messages of names_per_message at feed_rate_s names/s."""
        carry = 0.0
        while True:
            carry += self.config.feed_rate_s * TICK_S
            names = int(carry)
            carry -= names
            for _ in range(names):
                payload = self._pool[self._pool_cursor % len(self._pool)]
                self._pool_cursor += 1
                self._out_batch.append(payload)
                if len(self._out_batch) >= self.config.names_per_message:
                    await self._ship()
            await asyncio.sleep(TICK_S)

    async def _ship(self) -> None:
        payloads = self._out_batch
        self._out_batch = []
        partition = self._round_robin % self.config.partitions
        self._round_robin += 1
        await self._delivery.put((partition, self._batch_offset, payloads))
        self._batch_offset += 1
        self.feed_produced += len(payloads)
        self.produced_per_partition[partition] += len(payloads)

    async def _parse(self, payload: bytes) -> ToScrapeStruct | Exception:
        """orjson + pydantic on the serial core; charged per name."""
        try:
            record = ToScrapeStruct.model_validate(orjson.loads(payload))
        except ValidationError as ve:
            return ve
        if self.config.parse_cost_s > 0.0:
            await self.machine.cpu.work(self.config.parse_cost_s, what="kafka-parse")
        return record

    async def consume_one(self) -> ToScrapeStruct | Exception:
        """Next record: continuation names cost parse only; a fresh
        message pays the blocked wait + fetch RTT for all its names."""
        stage = self.state.stage("kafka_get")
        if self._pending:
            # served from the client-side buffer of the last fetch: no
            # broker round trip, and its offset commit is already owed
            t0 = self.state.now()
            record = await self._parse(self._pending.popleft())
            if isinstance(record, Exception):
                return record
            self.consumed += 1
            stage.add(self.state.now() - t0)
            return record
        t0 = self.state.now()
        partition, _offset, payloads = await self._delivery.get()
        t_data = self.state.now()
        connection: asyncio.Semaphore | nullcontext = (
            self._connections if self._connections is not None else nullcontext()
        )
        async with connection:
            if self.config.fetch_cost_s > 0.0:
                await asyncio.sleep(self.config.fetch_cost_s)
            n_bytes = sum(len(p) for p in payloads)
            io = await self.machine.network.fetch(n_bytes=n_bytes)
            self.bytes_transferred += n_bytes
        if io.error is not None:
            # dropped fetch: the worker's error path stalls it for 10s
            self.fetch_failures += 1
            return io.error
        self._pending.extend(payloads[1:])
        self._uncommitted += 1
        self.messages_consumed += 1
        self.consumed_per_partition[partition] += len(payloads)
        record = await self._parse(payloads[0])
        if isinstance(record, Exception):
            return record
        self.consumed += 1
        stage.add(self.state.now() - t0, blocked_s=t_data - t0)
        return record

    async def consume_many(self, count: int) -> list[ToScrapeStruct] | Exception:
        """Bulk consumer fetch: aiokafka's getmany returns up to
        `count` buffered records with one broker round trip, so the
        fetch RTT and the transfer amortize over the whole batch; each
        name still pays orjson+pydantic parse on the serial core. The
        blocked wait models the consumer parking when the feed is slow.
        """
        stage = self.state.stage("kafka_get")
        t0 = self.state.now()
        partition, _offset, payloads = await self._delivery.get()
        t_data = self.state.now()
        batches = [(partition, payloads)]
        # buffered drain: messages already delivered cost no extra RTT
        while len(batches) < count:
            try:
                p, _o, pl = self._delivery.get_nowait()
            except asyncio.QueueEmpty:
                break
            batches.append((p, pl))

        connection: asyncio.Semaphore | nullcontext = (
            self._connections if self._connections is not None else nullcontext()
        )
        async with connection:
            if self.config.fetch_cost_s > 0.0:
                await asyncio.sleep(self.config.fetch_cost_s)
            n_bytes = sum(len(p) for _, pls in batches for p in pls)
            io = await self.machine.network.fetch(n_bytes=n_bytes)
            self.bytes_transferred += n_bytes
        if io.error is not None:
            self.fetch_failures += 1
            return io.error

        for p, pls in batches:
            self._uncommitted += 1
            self.messages_consumed += 1
            self.consumed_per_partition[p] += len(pls)

        out: list[ToScrapeStruct] = []
        for _p, pls in batches:
            for payload in pls:
                record = await self._parse(payload)
                if isinstance(record, Exception):
                    # matches the real adapter: a poison record aborts
                    # the batch, offsets stay uncommitted, redelivery
                    # follows
                    return record
                self.consumed += 1
                out.append(record)
        stage.add(self.state.now() - t0, blocked_s=t_data - t0)
        return out

    async def commit(self) -> None:
        """One broker RTT that clears every fetched message at once.

        The pipeline commits once per consume batch, so all messages
        fetched since the last commit are covered by a single round
        trip; that is what takes the commit RTT off the per-player path.
        """
        if self._uncommitted <= 0:
            return
        stage = self.state.stage("commit")
        t0 = self.state.now()
        connection: asyncio.Semaphore | nullcontext = (
            self._connections if self._connections is not None else nullcontext()
        )
        async with connection:
            async with self._commit_lock:
                t_locked = self.state.now()
                if self.config.commit_cost_s > 0.0:
                    await asyncio.sleep(self.config.commit_cost_s)
                io = await self.machine.network.fetch(n_bytes=64)
                self.bytes_transferred += 64
                if io.error is not None:
                    # failed commit: the offsets stay owed for retry
                    self.commit_failures += 1
                else:
                    self.commits += 1
                    self._uncommitted = 0
        stage.add(self.state.now() - t0, blocked_s=t_locked - t0)

    async def produce(self, message: BaseModel, key: str | None = None) -> None:
        """Serialize then pay the broker round trip."""
        stage = self.state.stage("produce")
        t0 = self.state.now()
        if self.config.serialize_cost_s > 0.0:
            await self.machine.cpu.work(
                self.config.serialize_cost_s, what="kafka-serialize"
            )
        payload = orjson.dumps(
            message.model_dump(exclude_none=True)
            if self.config.exclude_none_fields
            else message.model_dump()
        )
        if self.config.produce_cost_s > 0.0:
            await asyncio.sleep(self.config.produce_cost_s)
        partition = self._partition(key)
        self.produced_per_partition[partition] += 1
        self.produced_total += 1
        if isinstance(message, ToScrapeStruct):
            # requeued names re-enter the topic as singleton messages
            self.requeues += 1
            if self.feed:
                await self._delivery.put((partition, self._batch_offset, [payload]))
                self._batch_offset += 1
        stage.add(self.state.now() - t0)


class SimQueueBackend(QueueBackendProtocol[ToScrapeStruct]):
    """Consumer + producer over one SimKafka topic, like the real
    adapter: the scraper re-enqueues failures into the topic it eats
    from, so the to_scrape queue needs both surfaces.
    """

    def __init__(self, kafka: SimKafka) -> None:
        self._kafka = kafka

    async def start(self) -> None:
        await self._kafka.start_feed()

    async def stop(self) -> None:
        await self._kafka.stop_feed()

    async def put(self, messages: list[ToScrapeStruct]) -> Exception | None:
        for message in messages:
            await self._kafka.produce(message)
        return None

    async def get_one(self) -> ToScrapeStruct | Exception | None:
        return await self._kafka.consume_one()

    async def get_many(self, count: int) -> list[ToScrapeStruct] | Exception:
        return await self._kafka.consume_many(count)

    async def commit(self) -> Exception | None:
        await self._kafka.commit()
        return None


class SimProducerBackend(QueueBackendProducerProtocol[BaseModel]):
    """QueueBackendProducerProtocol over a SimKafka topic."""

    def __init__(self, kafka: SimKafka) -> None:
        self._kafka = kafka

    async def start(self) -> None:
        await self._kafka.start_feed()

    async def stop(self) -> None:
        await self._kafka.stop_feed()

    async def put(self, messages: list[BaseModel]) -> Exception | None:
        for message in messages:
            key = None
            if isinstance(message, ScrapedStruct):
                key = str(message.player_data.id % 10)
            await self._kafka.produce(message, key=key)
        return None


class SimProxyManager:
    """In-memory stand-in: `proxies` proxies in a flat list, rotation is a counter.

    get_proxy(None) returns the whole list, matching the real manager,
    because fetchers read the list each iteration and pick their sticky
    index modulo its length.
    """

    def __init__(self, count: int, state: RunState) -> None:
        self.proxy_list = [f"http://user:pass@sim{i}.proxy:1080" for i in range(count)]
        self.state = state
        self.rotations = 0

    async def get_proxy(
        self, index: int | None = None
    ) -> tuple[str | list[str] | None, Exception | None]:
        stage = self.state.stage("proxy_get")
        if index is None:
            stage.calls += 1  # no virtual cost: a lock and a list copy
            return list(self.proxy_list), None
        if not (0 <= index < len(self.proxy_list)):
            return None, IndexError("proxy index out of range")
        stage.calls += 1
        return self.proxy_list[index], None

    async def rotate_proxies(self) -> None:
        self.rotations += 1


class SimHiscoreAPI:
    """Jagex stand-in: seeded per-fetch outcomes and latencies.

    The rate limiter stays real (ProxyRuntime builds one per proxy from
    ProxySettings defaults, shared by every fetcher assigned to that
    proxy); check() time is accounted so rate-limit waits show up in
    the stage shares.
    """

    config: ScraperThroughputConfig
    state: RunState
    rng: random.Random
    sigma: float  # lognormal sigma: not_found tail from p99/p50

    def __init__(self, rate_limiter: RateLimiter | None = None) -> None:
        self.rate_limiter = rate_limiter or RateLimiter(
            windows=[Window(name="default", count=60, interval_ms=60_000)]
        )

    async def get(
        self, player: str, session: Any, proxy: str | None = None
    ) -> Ok | Err:
        state = self.state
        cfg = self.config
        stage = state.stage("rate_limit")
        t0 = state.now()
        await self.rate_limiter.check()
        stage.add(state.now() - t0)

        roll = self.rng.random() * 100.0
        fetch = state.stage("fetch")
        t1 = state.now()
        if roll < cfg.not_found_pct:
            # prod p50/p99 sit inside the not_found distribution (the
            # majority outcome): lognormal with median 1.7s, p99 5s
            latency = self.rng.lognormvariate(
                math.log(cfg.not_found_latency_s), self.sigma
            )
            state.fetch_samples["not_found"].append(latency)
            await asyncio.sleep(latency)
            fetch.add(state.now() - t1)
            state.outcomes.not_found += 1
            return Err(
                error=PlayerDoesNotExist(f"Player '{player}' does not exist."),
                latency=latency,
            )
        if roll < cfg.not_found_pct + cfg.error_pct:
            latency = _jittered(self.rng, cfg.error_latency_s, cfg.latency_jitter)
            state.fetch_samples["error"].append(latency)
            await asyncio.sleep(latency)
            fetch.add(state.now() - t1)
            state.outcomes.errors += 1
            return Err(error=Exception("sim jagex 502"), latency=latency)
        latency = _jittered(self.rng, cfg.success_latency_s, cfg.latency_jitter)
        state.fetch_samples["success"].append(latency)
        await asyncio.sleep(latency)
        fetch.add(state.now() - t1)
        state.outcomes.scraped += 1
        stats = PlayerStats(
            skills=[Skill(id=0, name="overall", rank=1, level=2, xp=3)],
            activities=[Activity(id=7, name="clue_all", rank=1, score=1)],
        )
        return Ok(value=stats, latency=latency)


def build_payload_pool(pool_size: int, exclude_none: bool = False) -> list[bytes]:
    """Deterministic serialized ToScrapeStruct records, cycled by offset."""
    pool: list[bytes] = []
    for i in range(pool_size):
        player = PlayerStruct(
            id=i + 1,
            name=f"sim_player_{i}",
            created_at=datetime(2024, 1, 1),
        )
        record = ToScrapeStruct(
            metadata=MetaData(version=1, source="sim"),
            player_data=player,
        )
        dump = (
            record.model_dump(exclude_none=True)
            if exclude_none
            else record.model_dump()
        )
        pool.append(orjson.dumps(dump))
    return pool


def _timed(
    state: RunState, stage_name: str, fn: Callable[..., Coroutine[Any, Any, Any]]
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Wrap an async product function, charging its duration to a stage."""

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        t0 = state.now()
        try:
            return await fn(*args, **kwargs)
        finally:
            state.stage(stage_name).add(state.now() - t0)

    return wrapper


async def main(**kwargs) -> ScraperThroughputReport:
    """Run the real scraper pipeline against the simulated broker."""
    config = ScraperThroughputConfig(**kwargs)
    with virtual_time():
        logging.getLogger("bot_detector").setLevel(logging.ERROR)
        machine = Machine(
            MachineConfig(
                seed=config.machine_seed,
                network=NetworkConfig(
                    mean_ms=0.01,
                    jitter_ms=0.005,
                    bandwidth_mbps=config.kafka_bandwidth_mbps,
                ),
            )
        )
        state = RunState(machine)
        rng = random.Random(config.seed)

        broker = SimKafka(machine, config, state, feed=True)
        not_found_broker = SimKafka(machine, config, state, feed=False)
        scraped_broker = SimKafka(machine, config, state, feed=False)

        ts_queue = Queue[ToScrapeStruct](
            SimQueueBackend(broker), name="players.to_scrape"
        )
        nf_producer = QueueProducer[NotFoundStruct](
            SimProducerBackend(not_found_broker), name="players.not_found"
        )
        sc_producer = QueueProducer[ScrapedStruct](
            SimProducerBackend(scraped_broker), name="players.scraped"
        )

        # patch the base's I/O seams; the stage functions run unmodified
        SimHiscoreAPI.config = config
        SimHiscoreAPI.state = state
        SimHiscoreAPI.rng = rng
        SimHiscoreAPI.sigma = math.log(config.latency_p99_over_p50) / Z_99
        original_api = scraper_fetcher.HiscoreOldSchoolAPI
        original_transform = scraper_processor.transform_player_stats
        scraper_fetcher.HiscoreOldSchoolAPI = SimHiscoreAPI  # type: ignore[assignment]
        scraper_processor.transform_player_stats = _timed(
            state, "transform", original_transform
        )

        proxy_manager = SimProxyManager(config.proxies, state)
        runtime = ProxyRuntime(proxy_manager=proxy_manager)  # type: ignore[arg-type]
        await ts_queue.start()
        await nf_producer.start()
        await sc_producer.start()

        task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(
            maxsize=config.task_queue_maxsize
        )
        results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(
            maxsize=config.results_queue_maxsize
        )

        # a crashed stage task must fail the run, not silently shrink
        # the pipeline (a dead stage looks like a throughput drop)
        stage_errors: list[BaseException] = []

        def guarded(coro: Coroutine[Any, Any, None], name: str) -> asyncio.Task:
            async def run() -> None:
                try:
                    await coro
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # surface sim-wiring bugs
                    stage_errors.append(exc)

            return asyncio.create_task(run(), name=name)

        stages = [
            guarded(
                scraper_consumer.consume(
                    player_ts_queue=ts_queue,
                    task_queue=task_queue,
                    batch_size=config.consume_batch_size,
                ),
                name="scraper-consumer",
            )
        ]
        for fetcher_id in range(config.fetchers):
            stages.append(
                guarded(
                    scraper_fetcher.fetch(
                        fetcher_id=fetcher_id,
                        runtime=runtime,
                        task_queue=task_queue,
                        results_queue=results_queue,
                        session=None,  # type: ignore[arg-type]
                    ),
                    name=f"scraper-fetcher-{fetcher_id}",
                )
            )
        for processor_id in range(config.processors):
            stages.append(
                guarded(
                    scraper_processor.process(
                        processor_id=processor_id,
                        results_queue=results_queue,
                        player_ts_queue=ts_queue,
                        player_nf_producer=nf_producer,  # type: ignore[arg-type]
                        player_sc_producer=sc_producer,  # type: ignore[arg-type]
                    ),
                    name=f"scraper-processor-{processor_id}",
                )
            )

        await asyncio.sleep(config.duration_s)

        for stage_task in stages:
            stage_task.cancel()
        await asyncio.gather(*stages, return_exceptions=True)
        await ts_queue.stop()
        await nf_producer.stop()
        await sc_producer.stop()
        if stage_errors:
            raise RuntimeError(
                f"{len(stage_errors)} stage tasks crashed, first: {stage_errors[0]!r}"
            )

        # restore the seams so other scenarios in the process see product code
        scraper_fetcher.HiscoreOldSchoolAPI = original_api
        scraper_processor.transform_player_stats = original_transform

        consumed = broker.consumed
        # throughput counts completed fetches, not consumed names: the
        # pipeline buffers names between consume and fetch outcome
        # (task_queue, results_queue, one in-flight fetch per fetcher),
        # so consumed overstates the fetch rate by buffer / duration
        fetched = (
            state.outcomes.scraped + state.outcomes.not_found + state.outcomes.errors
        )
        busy_s = sum(stage.total_s for stage in state.stages.values())
        active_s = busy_s - sum(
            stage.blocked_s
            for name, stage in state.stages.items()
            if name in ("kafka_get", "commit")
        )
        iterations = max(consumed, 1)
        mean_active_s = active_s / iterations
        mean_iteration_s = busy_s / iterations
        # Little's law over the fetch pool: slots / mean per-player time
        # actually spent by the pool (rate-limit waits, proxy lookups and
        # fetch latency; transform and produce belong to the processors)
        fleet_cap_s = config.fetchers / mean_active_s if mean_active_s > 0 else 0.0
        # the consumer's only serial work is now one commit RTT and (on
        # a single broker connection) one fetch RTT per consume batch:
        # both amortize over batch x names_per_message players. Parse
        # stays per player on the buffered drain.
        per_batch_serial_s = config.commit_cost_s + (
            config.fetch_cost_s if config.kafka_connection_limit == 1 else 0.0
        )
        consumer_serial_s = per_batch_serial_s / (
            config.names_per_message * config.consume_batch_size
        )
        consumer_cap_s = (
            1.0 / consumer_serial_s if consumer_serial_s > 0 else float("inf")
        )
        # per-proxy windows bind at MAX_CALLS_PER_SECOND each
        rate_cap_s = float(config.proxies * ProxySettings().MAX_CALLS_PER_SECOND)
        throughput_s = fetched / config.duration_s

        caps = {
            "feed": float(config.feed_rate_s),
            "consumer": consumer_cap_s,
            "fleet": fleet_cap_s,
            "rate": rate_cap_s,
        }
        binding = min(caps, key=caps.get)  # type: ignore[arg-type]

        stages = {}
        for name, stage in state.stages.items():
            stat = StageStat(
                calls=stage.calls,
                total_s=stage.total_s,
                blocked_s=stage.blocked_s,
                share_pct=(100.0 * stage.total_s / busy_s) if busy_s > 0 else 0.0,
            )
            stages[name] = stat

        latency_stats = {}
        for outcome, samples in state.fetch_samples.items():
            ordered = sorted(samples)
            latency_stats[outcome] = FetchLatencyStat(
                calls=len(ordered),
                mean_s=(sum(ordered) / len(ordered)) if ordered else 0.0,
                p50_s=_pct(ordered, 0.50),
                p99_s=_pct(ordered, 0.99),
            )

        return ScraperThroughputReport(
            config=config,
            duration_s=config.duration_s,
            fetchers=config.fetchers,
            processors=config.processors,
            proxies=config.proxies,
            partitions=config.partitions,
            feed_produced=broker.feed_produced,
            requeues=broker.requeues,
            consumed=consumed,
            messages_consumed=broker.messages_consumed,
            backlog=broker.backlog,
            per_partition_produced=broker.produced_per_partition,
            per_partition_consumed=broker.consumed_per_partition,
            scraped_produced=scraped_broker.produced_total,
            not_found_produced=not_found_broker.produced_total,
            outcomes=state.outcomes,
            latency=latency_stats,
            commits=broker.commits,
            avg_name_bytes=broker.avg_name_bytes,
            bytes_transferred=broker.bytes_transferred,
            kafka_fetch_failures=broker.fetch_failures,
            kafka_commit_failures=broker.commit_failures,
            throughput_s=throughput_s,
            fleet_cap_s=fleet_cap_s,
            consumer_cap_s=consumer_cap_s,
            consumer_serial_s=consumer_serial_s,
            rate_cap_s=rate_cap_s,
            binding=binding,
            mean_iteration_s=mean_iteration_s,
            busy_stage_s=busy_s,
            stages=stages,
        )
