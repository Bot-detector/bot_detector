from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import TopicPartition
from aiokafka.structs import OffsetAndMetadata
from bot_detector.event_queue.adapters.kafka import KafkaLagProbe
from bot_detector.event_queue.core.errors import LagProbeError

TOPIC = "players"
GROUP = "group"


def _probe_with(
    partitions: set[int] | None,
    end_offsets: dict[TopicPartition, int],
    first_offsets: dict[TopicPartition, int],
    group_offsets: dict[TopicPartition, OffsetAndMetadata],
) -> KafkaLagProbe:
    probe = KafkaLagProbe(bootstrap_servers="localhost:9092")
    probe._consumer = MagicMock()
    probe._consumer.partitions_for_topic = MagicMock(return_value=partitions)
    probe._consumer.end_offsets = AsyncMock(return_value=end_offsets)
    probe._consumer.beginning_offsets = AsyncMock(return_value=first_offsets)
    probe._admin = MagicMock()
    probe._admin.list_consumer_group_offsets = AsyncMock(return_value=group_offsets)
    return probe


@pytest.mark.asyncio
async def test_lag_not_started_raises():
    probe = KafkaLagProbe(bootstrap_servers="localhost:9092")

    with pytest.raises(LagProbeError, match="not started"):
        await probe.lag(topic=TOPIC, group_id=GROUP)


@pytest.mark.asyncio
async def test_lag_metadata_unavailable_raises():
    # partitions_for_topic returning None (broker down, topic absent) must
    # raise, not report lag=0 — zero lag reads as false-healthy
    probe = _probe_with(
        partitions=None, end_offsets={}, first_offsets={}, group_offsets={}
    )

    with pytest.raises(LagProbeError, match="No partitions"):
        await probe.lag(topic=TOPIC, group_id=GROUP)


@pytest.mark.asyncio
async def test_lag_sums_committed_and_uncommitted_partitions():
    tp0 = TopicPartition(TOPIC, 0)
    tp1 = TopicPartition(TOPIC, 1)
    probe = _probe_with(
        partitions={0, 1},
        end_offsets={tp0: 10, tp1: 10},
        first_offsets={tp0: 0, tp1: 0},
        # group committed on tp0 only; tp1 never consumed
        group_offsets={tp0: OffsetAndMetadata(8, "")},
    )

    lag = await probe.lag(topic=TOPIC, group_id=GROUP)

    assert lag == 2 + 10


@pytest.mark.asyncio
async def test_lag_truncated_partition_counts_zero():
    tp0 = TopicPartition(TOPIC, 0)
    probe = _probe_with(
        partitions={0},
        end_offsets={tp0: 3},
        first_offsets={tp0: 5},
        group_offsets={},
    )

    # end < first (topic recreated): partition contributes zero lag
    lag = await probe.lag(topic=TOPIC, group_id=GROUP)

    assert lag == 0
