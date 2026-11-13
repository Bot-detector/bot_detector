import asyncio
import logging
import math
import os
import random
from collections import deque
from collections.abc import Callable, Coroutine
from contextlib import nullcontext
from typing import Any

os.environ.setdefault("PROXY_API_KEY", "sim")  # ProxySettings is required-env

import orjson  # noqa: E402
from aiokafka.errors import KafkaTimeoutError  # noqa: E402
from bot_detector.event_queue.core import (  # noqa: E402
    Queue,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
    QueueProducer,
)
from bot_detector.event_queue.structs import (  # noqa: E402
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.hiscore_scraper.flow import consumer as scraper_consumer  # noqa: E402
from bot_detector.hiscore_scraper.flow import fetcher as scraper_fetcher  # noqa: E402
from bot_detector.hiscore_scraper.flow import (
    processor as scraper_processor,  # noqa: E402
)
from bot_detector.hiscore_scraper.flow.structs import FetchResult  # noqa: E402
from bot_detector.hiscore_scraper.proxy_pool import (
    runtime as scraper_runtime,  # noqa: E402
)
from bot_detector.hiscore_scraper.proxy_pool.runtime import ProxyRuntime  # noqa: E402
from bot_detector.osrs_hs_api.exceptions import (  # noqa: E402
    Err,
    Ok,
    PlayerDoesNotExist,
)
from bot_detector.osrs_hs_api.structs import (  # noqa: E402
    EXPECTED_SKILL_IDS,
    Activity,
    PlayerStats,
    Skill,
)
from bot_detector.proxy_manager import Settings as ProxySettings  # noqa: E402
from bot_detector.rate_limiter import RateLimiter, Window  # noqa: E402
from pydantic import BaseModel, Field, ValidationError, model_validator  # noqa: E402

from dst import virtual_time  # noqa: E402
from dst.clock import VirtualClock  # noqa: E402
from dst.loop import running_clock  # noqa: E402
from dst.payloads import build_toscrape_pool  # noqa: E402
from dst.systems import (  # noqa: E402
    CpuCosts,
    LinkCosts,
    SimBroker,
    SimBrokerConfig,
    SimMessage,
)

logger = logging.getLogger(__name__)

TICK_S = 0.01  # feed pacing granularity, matches SimBroker's feed tick
Z_99 = 2.3263478740408408  # standard-normal z-score at p99

_TOPIC = "to_scrape"
_GROUP = "scraper"

# fake-owned broker link profile: the sub-RTT wiggle the retired
# Machine network model supplied (mean 0.01ms +- 0.005ms), now drawn
# per attempt on a dedicated counter-based fault stream
_LINK_MEAN_MS = 0.01
_LINK_JITTER_MS = 0.005
_NET_STREAM = "s:net:to_scrape"


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
    # single connection. RTTs pay the fake-owned link costs
    # (LinkCosts jitter + kafka_bandwidth_mbps transfer), so link
    # loss surfaces as fetch failures on broker traffic as well.
    kafka_connection_limit: int = Field(default=0, ge=0)
    kafka_payload_bytes: int = Field(default=512, ge=1)
    # broker link bandwidth: 800 Mbps = 100 MB/s (prod-plausible LAN link).
    # Transfer time per message = bytes * 8 / bandwidth, on top of the
    # explicit RTT costs.
    kafka_bandwidth_mbps: float = Field(default=800.0, gt=0.0)
    # drop null fields (ironman/hardcore_ironman/ultimate_ironman/
    # normalized_name) from serialized messages to shrink them
    exclude_none_fields: bool = False
    # simulated jagex fetch outcomes, calibrated to the Nov 2026 Grafana
    # panel (hiscore_scraper_fetch_latency, 6h): each outcome is
    # lognormal anchored at its panel p50 (`*_latency_s`) and p99
    # (`*_p99_over_p50`):
    #   success    p50 1.45  p90 ~3.2  p99 ~6.1  (fattest tail)
    #   not_found  p50 1.45  p90 ~2.7  p99 ~4.5
    #   error      p50 0.33  p90 ~0.9  p99 ~2.2  (failures are fast)
    # (lognormal through the p50/p99 anchors runs slightly wide at p90:
    # 3.2 vs the panel's 2.4 for success - prod's tail is a mixture)
    not_found_pct: float = Field(default=54.5, ge=0.0, le=100.0)
    error_pct: float = Field(default=2.0, ge=0.0, le=100.0)
    success_latency_s: float = Field(default=1.45, ge=0.0)
    success_p99_over_p50: float = Field(default=4.2, gt=1.0)
    not_found_latency_s: float = Field(default=1.45, ge=0.0)
    not_found_p99_over_p50: float = Field(default=3.1, gt=1.0)
    error_latency_s: float = Field(default=0.33, ge=0.0)
    error_p99_over_p50: float = Field(default=6.7, gt=1.0)
    # hard client timeout: any draw at or above it lands on it exactly
    # (a fetch is never observed past the timeout) and surfaces as an
    # error regardless of its original outcome - in prod a timed-out
    # scrape raises, it does not return partial data
    timeout_s: float = Field(default=30.0, gt=0.0)
    # share of error fetches that hard-timeout while a degradation
    # episode is active: proxy failures burst inside a fleet-wide
    # slowdown, which is the flat-top 30s error p99 in prod panels.
    # Outside episodes errors keep their lognormal draw.
    error_timeout_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    # fleet-wide degradation episodes: prod shows a few minutes-long
    # bumps per ~6h where every outcome's percentiles rise ~2-3x
    # together. Exponential inter-arrival and duration, uniform
    # multiplier. Episodes draw from their own RNG stream (seed + 1),
    # so outcome draws do not shift when the schedule knobs change.
    degradation_every_s: float = Field(default=7200.0, gt=0.0)
    degradation_duration_s: float = Field(default=240.0, gt=0.0)
    degradation_factor_min: float = Field(default=1.8, ge=1.0)
    degradation_factor_max: float = Field(default=3.0, ge=1.0)

    @model_validator(mode="after")
    def check_outcome_mix(self):
        if self.not_found_pct + self.error_pct > 100.0:
            raise ValueError(
                f"not_found_pct + error_pct must be <= 100, got "
                f"{self.not_found_pct} + {self.error_pct}"
            )
        return self

    @model_validator(mode="after")
    def check_degradation_factor(self):
        if self.degradation_factor_min > self.degradation_factor_max:
            raise ValueError(
                f"degradation_factor_min must be <= degradation_factor_max, "
                f"got {self.degradation_factor_min} > {self.degradation_factor_max}"
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
    timeouts: int = 0  # errors that landed on the client timeout


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
    outcomes: OutcomeCounts
    latency: dict[str, FetchLatencyStat]
    commits: int
    avg_name_bytes: float
    bytes_transferred: int
    kafka_fetch_failures: int
    kafka_commit_failures: int
    degradation_episodes: int
    degradation_active_s: float
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
        ]
        if self.degradation_episodes:
            lines.append(
                f"degradation: {self.degradation_episodes} episode(s), "
                f"{self.degradation_active_s:.1f}s of {self.duration_s:.0f}s "
                f"active, {self.outcomes.timeouts} client timeouts"
            )
        lines += [
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

    def __init__(self, clock: VirtualClock) -> None:
        assert isinstance(clock, VirtualClock), f"not a clock: {clock!r}"
        self.clock = clock
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


class _Degradation:
    """Fleet-wide slow episodes on the virtual clock.

    Prod panels show a few minutes-long bumps per ~6h where every
    outcome's percentiles rise together ~2-3x. Modeled as an on/off
    process: exponential inter-arrival (`degradation_every_s`) and
    duration (`degradation_duration_s`), uniform multiplier in
    [degradation_factor_min, degradation_factor_max]. State advances
    lazily off `now()` - the clock only moves when the pipeline awaits,
    so no timers ride the loop - and the schedule draws from its own
    RNG stream, keeping outcome draws independent of episode knobs.
    """

    def __init__(self, rng: random.Random, config: ScraperThroughputConfig) -> None:
        self._rng = rng
        self._every_s = config.degradation_every_s
        self._duration_mean_s = config.degradation_duration_s
        self._factor_min = config.degradation_factor_min
        self._factor_max = config.degradation_factor_max
        self._next_start_s = rng.expovariate(1.0 / self._every_s)
        self._active_end_s = -1.0  # no episode in progress
        self._active_factor = 1.0
        self.spans: list[tuple[float, float]] = []  # (start, end) per episode

    def factor(self, now_s: float) -> float:
        """The multiplier applying at `now_s`: 1.0 outside episodes."""
        if now_s < self._active_end_s:
            return self._active_factor
        while now_s >= self._next_start_s:
            # lazy advance: the clock may jump past whole episodes
            start = self._next_start_s
            duration = self._rng.expovariate(1.0 / self._duration_mean_s)
            end = start + duration
            factor = self._rng.uniform(self._factor_min, self._factor_max)
            self.spans.append((start, end))
            self._next_start_s = end + self._rng.expovariate(1.0 / self._every_s)
            if now_s < end:
                self._active_end_s = end
                self._active_factor = factor
                return factor
        return 1.0

    def active_s(self, horizon_s: float) -> float:
        """Total episode time within [0, horizon_s] of virtual time."""
        return sum(max(0.0, min(end, horizon_s) - start) for start, end in self.spans)


class SimKafka:
    """One simulated topic over a SimBroker log: paced multi-partition
    feed + consumer path.

    SimBroker owns the partitioned log, the offsets and the backlog
    (partitions/pacing/backlog moved onto it when the kafka fakes
    were consolidated). This class keeps what the scraper pipeline
    uniquely models: names packed `names_per_message` per kafka
    message (joined with b"\\n" — orjson dumps never contain raw
    newlines — and split back at parse time), the client-side pending
    buffer of a partially consumed message, and the cost charging:
    the consumer surface mirrors what the real adapter does per
    message — a blocked wait for data (all workers park here when the
    consumer is the bottleneck), a fetch round trip paid to the
    fake-owned `LinkCosts` link (jitter + `kafka_bandwidth_mbps`
    transfer), then real orjson + pydantic parsing charged to the
    fake's serial-cost counter. commit() is a broker RTT under a
    single-flight lock: one consumer instance serializes every
    worker's per-batch commit, exactly the real adapter's shape. RTTs
    flow through a `kafka_connection_limit` connection pool
    (0 = unlimited).
    """

    def __init__(
        self,
        config: ScraperThroughputConfig,
        state: RunState,
        *,
        feed: bool,
    ):
        assert isinstance(state, RunState), f"not a RunState: {state!r}"
        self.config = config
        self.state = state
        self.feed = feed
        self._broker = SimBroker(
            SimBrokerConfig(seed=config.seed, payload_bytes=config.kafka_payload_bytes)
        )
        self._link = LinkCosts(
            seed=config.seed,
            stream=_NET_STREAM,
            mean_ms=_LINK_MEAN_MS,
            jitter_ms=_LINK_JITTER_MS,
            bandwidth_mbps=config.kafka_bandwidth_mbps,
        )
        self._cpu = CpuCosts()
        self._pending: deque[bytes] = deque()  # names left in the fetched batch
        self._uncommitted = 0  # fetched messages awaiting their one commit
        self._commit_lock = asyncio.Lock()
        limit = config.kafka_connection_limit
        self._connections: asyncio.Semaphore | None = (
            asyncio.Semaphore(limit) if limit > 0 else None
        )
        self._pacer: asyncio.Task[None] | None = None
        self._pool = build_toscrape_pool(config.pool_size, config.exclude_none_fields)
        self.avg_name_bytes = sum(len(p) for p in self._pool) / len(self._pool)
        self._pool_cursor = 0
        self._out_batch: list[bytes] = []
        self._round_robin = 0  # shared: feed ships and keyless requeues
        self._read_cursor = 0  # round-robin read position over partitions
        self.feed_produced = 0
        self.produced_total = 0
        self.requeues = 0
        self.consumed = 0
        self.messages_consumed = 0
        self.commits = 0
        self.bytes_transferred = 0
        self.fetch_failures = 0
        self.commit_failures = 0
        self.consumed_per_partition = [0] * config.partitions

    @property
    def backlog(self) -> int:
        """Unconsumed to_scrape records: feed + requeues - consumed."""
        return self.feed_produced + self.requeues - self.consumed

    @property
    def produced_per_partition(self) -> list[int]:
        """Messages produced per partition: the SimBroker watermarks."""
        return [
            self._broker.high_watermark(_TOPIC, p)
            for p in range(self.config.partitions)
        ]

    def _partition(self, key: str | None) -> int:
        if key is not None:
            return int(key) % self.config.partitions
        partition = self._round_robin % self.config.partitions
        self._round_robin += 1
        return partition

    def _broker_lag(self) -> int:
        """Total unconsumed messages across the topic's partitions."""
        return sum(
            self._broker.lag(_TOPIC, p, _GROUP) for p in range(self.config.partitions)
        )

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
        """Pack names into messages of names_per_message at feed_rate_s names/s.

        The pacer parks while the SimBroker backlog reaches max_buffer,
        the same bound the old private delivery queue applied.
        """
        carry = 0.0
        while True:
            carry += self.config.feed_rate_s * TICK_S
            names = int(carry)
            carry -= names
            if names > 0:
                while self._broker_lag() >= self.config.max_buffer:
                    await asyncio.sleep(TICK_S)
                for _ in range(names):
                    payload = self._pool[self._pool_cursor % len(self._pool)]
                    self._pool_cursor += 1
                    self._out_batch.append(payload)
                    if len(self._out_batch) >= self.config.names_per_message:
                        await self._ship()
            await asyncio.sleep(TICK_S)

    async def _ship(self) -> None:
        """Ship one packed message into the SimBroker log."""
        payloads = self._out_batch
        self._out_batch = []
        partition = self._round_robin % self.config.partitions
        self._round_robin += 1
        error = await self._broker.produce(_TOPIC, partition, b"\n".join(payloads))
        if error is not None:
            # unreachable with the scenario's all-zero fault table; a
            # dropped feed message would silently skew every counter
            raise RuntimeError(f"sim broker feed rejected a payload: {error}")
        self.feed_produced += len(payloads)

    async def _pull(self, count: int) -> list[SimMessage]:
        """Round-robin pull of up to `count` messages across partitions.

        One SimBroker read per partition; the read cursor rotates so a
        consumer draining only the first partition cannot starve the
        rest (the feed round-robins writes the same way).
        """
        out: list[SimMessage] = []
        start = self._read_cursor
        last = start
        for i in range(self.config.partitions):
            if len(out) >= count:
                break
            partition = (start + i) % self.config.partitions
            batch = await self._broker.get_many(
                _TOPIC, partition, _GROUP, count - len(out)
            )
            if batch:
                last = partition
                out.extend(self._message(item) for item in batch)
        # resume after the partition that filled the batch, so the read
        # cursor keeps rotating instead of pinning one partition
        self._read_cursor = (last + 1) % self.config.partitions
        return out

    async def _parse(self, payload: bytes) -> ToScrapeStruct | Exception:
        """orjson + pydantic on the fake's serial-cost counter; per name."""
        try:
            record = ToScrapeStruct.model_validate(orjson.loads(payload))
        except ValidationError as ve:
            return ve
        if self.config.parse_cost_s > 0.0:
            await self._cpu.work(self.config.parse_cost_s)
        return record

    def _message(self, item: SimMessage | Exception) -> SimMessage:
        """Narrow a broker fetch result; faults are impossible here.

        The scenario runs the broker with an all-zero fault table, so
        a fault value would mean a SimBroker bug.
        """
        assert isinstance(item, SimMessage), f"unexpected broker fault: {item}"
        return item

    def _record_names(self, message: SimMessage) -> list[bytes]:
        """Unpack one kafka message into its per-name payloads."""
        names = message.payload.split(b"\n")
        self._uncommitted += 1
        self.messages_consumed += 1
        self.consumed_per_partition[message.partition] += len(names)
        return names

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
        while self._broker_lag() <= 0:
            # stopped feed with nothing in flight: return the drained
            # error instead of spinning (a parked loop would defeat
            # DSTIdleError by keeping the virtual loop non-idle)
            if self._broker.feed_started and not self._broker.feed_running:
                return KafkaTimeoutError("to_scrape drained: feed stopped")
            await asyncio.sleep(TICK_S)
        t_data = self.state.now()
        fetched = await self._pull(1)
        message = self._message(fetched[0])
        connection: asyncio.Semaphore | nullcontext = (
            self._connections if self._connections is not None else nullcontext()
        )
        async with connection:
            if self.config.fetch_cost_s > 0.0:
                await asyncio.sleep(self.config.fetch_cost_s)
            n_bytes = len(message.payload)
            error = await self._link.fetch(n_bytes=n_bytes)
            self.bytes_transferred += n_bytes
        if error is not None:
            # dropped fetch: the worker's error path stalls it for 10s
            self.fetch_failures += 1
            return error
        names = self._record_names(message)
        self._pending.extend(names[1:])
        record = await self._parse(names[0])
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
        while self._broker_lag() <= 0:
            if self._broker.feed_started and not self._broker.feed_running:
                return KafkaTimeoutError("to_scrape drained: feed stopped")
            await asyncio.sleep(TICK_S)
        t_data = self.state.now()
        messages = await self._pull(count)

        connection: asyncio.Semaphore | nullcontext = (
            self._connections if self._connections is not None else nullcontext()
        )
        async with connection:
            if self.config.fetch_cost_s > 0.0:
                await asyncio.sleep(self.config.fetch_cost_s)
            n_bytes = sum(len(m.payload) for m in messages)
            error = await self._link.fetch(n_bytes=n_bytes)
            self.bytes_transferred += n_bytes
        if error is not None:
            self.fetch_failures += 1
            return error

        names_per_message = [self._record_names(m) for m in messages]
        out: list[ToScrapeStruct] = []
        for names in names_per_message:
            for payload in names:
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
                error = await self._link.fetch(n_bytes=64)
                self.bytes_transferred += 64
                if error is not None:
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
            await self._cpu.work(self.config.serialize_cost_s)
        payload = orjson.dumps(
            message.model_dump(exclude_none=True)
            if self.config.exclude_none_fields
            else message.model_dump()
        )
        if self.config.produce_cost_s > 0.0:
            await asyncio.sleep(self.config.produce_cost_s)
        partition = self._partition(key)
        self.produced_total += 1
        if isinstance(message, ToScrapeStruct):
            # requeued names re-enter the topic as singleton messages
            self.requeues += 1
            if self.feed:
                error = await self._broker.produce(_TOPIC, partition, payload)
                if error is not None:
                    raise RuntimeError(f"sim broker rejected a requeue: {error}")
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
    the stage shares. Each outcome draws lognormal on the panel
    calibration in the config; the client timeout caps every draw,
    degradation episodes stretch them together, and error draws burst
    to the timeout inside an episode (the flat-top 30s error p99).
    """

    config: ScraperThroughputConfig
    state: RunState
    rng: random.Random
    degradation: _Degradation
    sigma_success: float  # lognormal sigmas: tails from p99/p50
    sigma_not_found: float
    sigma_error: float

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
        if roll < cfg.not_found_pct:
            kind = "not_found"
            latency = self.rng.lognormvariate(
                math.log(cfg.not_found_latency_s), self.sigma_not_found
            )
        elif roll < cfg.not_found_pct + cfg.error_pct:
            kind = "error"
            latency = self.rng.lognormvariate(
                math.log(cfg.error_latency_s), self.sigma_error
            )
        else:
            kind = "success"
            latency = self.rng.lognormvariate(
                math.log(cfg.success_latency_s), self.sigma_success
            )

        # a fleet-wide episode stretches every draw together
        factor = self.degradation.factor(state.now())
        latency *= factor
        timed_out = False
        # the client never observes a fetch past the timeout: capped
        # draws land on it exactly and surface as errors - in prod a
        # timed-out scrape raises, it does not return partial data
        if latency >= cfg.timeout_s:
            latency = cfg.timeout_s
            kind = "error"
            timed_out = True
            state.outcomes.timeouts += 1
        elif (
            kind == "error"
            and factor > 1.0
            and self.rng.random() * 100.0 < cfg.error_timeout_pct
        ):
            # proxy failures burst inside an episode: the flat-top 30s
            # error p99 in the prod panel
            latency = cfg.timeout_s
            timed_out = True
            state.outcomes.timeouts += 1

        state.fetch_samples[kind].append(latency)
        fetch = state.stage("fetch")
        t1 = state.now()
        await asyncio.sleep(latency)
        fetch.add(state.now() - t1)

        if kind == "not_found":
            state.outcomes.not_found += 1
            return Err(
                error=PlayerDoesNotExist(f"Player '{player}' does not exist."),
                latency=latency,
            )
        if kind == "error":
            state.outcomes.errors += 1
            error: Exception = (
                TimeoutError("sim jagex fetch timed out")
                if timed_out
                else Exception("sim jagex 502")
            )
            return Err(error=error, latency=latency)
        state.outcomes.scraped += 1
        stats = PlayerStats(
            skills=[
                Skill(id=i, name=f"skill_{i}", rank=1, level=2, xp=3)
                for i in sorted(EXPECTED_SKILL_IDS)
            ],
            activities=[Activity(id=7, name="clue_all", rank=1, score=1)],
        )
        return Ok(value=stats, latency=latency)


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
    """Run the real scraper pipeline against the simulated broker.

    The scraper runs as three stages wired by bounded asyncio queues:
    consume -> task_queue -> fetch pool -> results_queue -> processors.
    The real stage functions from ``bot_detector.hiscore_scraper`` run
    unmodified; only the I/O seams are replaced:

    - kafka: a SimKafka broker per topic, fed at ``feed_rate_s`` names
      per virtual second, packed ``names_per_message`` names per kafka
      message. Broker RTTs pay the fake-owned link costs through a
      ``kafka_connection_limit`` connection pool (0 = unlimited).
    - jagex: SimHiscoreAPI draws per-fetch outcomes on a seeded RNG,
      each lognormal on the panel calibration in the config fields,
      capped by the 30s client timeout, under fleet-wide degradation
      episodes that stretch every draw ~2-3x together.
    - proxies: an in-memory manager; fetchers are assigned sticky by
      index modulo the pool size, so each proxy's rate windows are
      shared by fetchers/proxies fetchers.

    Answers "where is the pipeline slow" with two lenses: stage-time
    shares, and the binding cap among feed, consumer serial path,
    fetch pool (Little's law: fetchers / mean fetch latency) and the
    per-proxy rate ceilings (proxies x 20/s).
    """
    config = ScraperThroughputConfig(**kwargs)
    with virtual_time():
        logging.getLogger("bot_detector").setLevel(logging.ERROR)
        clock = running_clock()
        state = RunState(clock)
        rng = random.Random(config.seed)

        broker = SimKafka(config, state, feed=True)
        scraped_broker = SimKafka(config, state, feed=False)

        ts_queue = Queue[ToScrapeStruct](
            SimQueueBackend(broker), name="players.to_scrape"
        )
        sc_producer = QueueProducer[ScrapedStruct](
            SimProducerBackend(scraped_broker), name="players.scraped"
        )

        SimHiscoreAPI.config = config
        SimHiscoreAPI.state = state
        SimHiscoreAPI.rng = rng
        SimHiscoreAPI.sigma_success = math.log(config.success_p99_over_p50) / Z_99
        SimHiscoreAPI.sigma_not_found = math.log(config.not_found_p99_over_p50) / Z_99
        SimHiscoreAPI.sigma_error = math.log(config.error_p99_over_p50) / Z_99
        SimHiscoreAPI.degradation = _Degradation(random.Random(config.seed + 1), config)
        original_api = scraper_runtime.HiscoreOldSchoolAPI
        original_transform = scraper_processor.transform_player_stats
        scraper_runtime.HiscoreOldSchoolAPI = SimHiscoreAPI  # type: ignore[assignment]
        scraper_processor.transform_player_stats = _timed(
            state, "transform", original_transform
        )
        # RetryTracker jitters every backoff from the process-global RNG;
        # seed it for the run (restored with the seams below) so two runs
        # of the same seed replay byte-identically
        original_random_state = random.getstate()
        random.seed(config.seed)

        proxy_manager = SimProxyManager(config.proxies, state)
        runtime = ProxyRuntime(proxy_manager=proxy_manager)  # type: ignore[arg-type]
        await ts_queue.start()
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
                        player_sc_producer=sc_producer,
                    ),
                    name=f"scraper-processor-{processor_id}",
                )
            )

        await asyncio.sleep(config.duration_s)

        for stage_task in stages:
            stage_task.cancel()
        await asyncio.gather(*stages, return_exceptions=True)
        await ts_queue.stop()
        await sc_producer.stop()

        def _restore_seams() -> None:
            # restore the seams so other scenarios in the process see
            # product code; must run on the crash path too, or a seeded
            # global RNG and patched functions leak into the process
            scraper_runtime.HiscoreOldSchoolAPI = original_api
            scraper_processor.transform_player_stats = original_transform
            random.setstate(original_random_state)

        if stage_errors:
            _restore_seams()
            raise RuntimeError(
                f"{len(stage_errors)} stage tasks crashed, first: {stage_errors[0]!r}"
            )

        _restore_seams()

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
        # the consumer's only serial work is one commit RTT and (on
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
            outcomes=state.outcomes,
            latency=latency_stats,
            commits=broker.commits,
            avg_name_bytes=broker.avg_name_bytes,
            bytes_transferred=broker.bytes_transferred,
            kafka_fetch_failures=broker.fetch_failures,
            kafka_commit_failures=broker.commit_failures,
            degradation_episodes=len(SimHiscoreAPI.degradation.spans),
            degradation_active_s=SimHiscoreAPI.degradation.active_s(config.duration_s),
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
