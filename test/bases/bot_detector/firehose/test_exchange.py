import asyncio

import pytest
from bot_detector.firehose.app.auth.auth import ANONYMOUS
from bot_detector.firehose.app.exchange import Exchange, Inbox, InboxClosed
from bot_detector.firehose.app.exchange.core import GRACE_S, KICK_CODE, KICK_REASON
from bot_detector.firehose.app.exchange.structs import QUEUE_MAX_SIZE
from prometheus_client import REGISTRY

TOPIC = "players.scraped"
GROUP = "fh-anonymous-players.scraped"


def make_exchange_with_inbox(
    conn_id: str = "c1", grace_s: float = GRACE_S
) -> tuple[Exchange, Inbox]:
    exchange = Exchange(grace_s=grace_s)
    inbox = exchange.subscribe(
        topic=TOPIC, group=GROUP, conn_id=conn_id, user=ANONYMOUS
    )
    return exchange, inbox


def test_subscribe_registers_and_get_inbox_round_trips():
    exchange, inbox = make_exchange_with_inbox()

    assert exchange.get_inbox("c1") is inbox
    assert exchange.get_subscribers(topic=TOPIC, group=GROUP) == ["c1"]


def test_send_delivers_a_copy_to_the_inbox():
    exchange, inbox = make_exchange_with_inbox()

    exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message="hello")

    assert inbox.queue.get_nowait() == "hello"


def test_send_drops_unknown_or_wrong_group_without_raising():
    exchange, inbox = make_exchange_with_inbox()

    exchange.send(conn_id="missing", topic=TOPIC, group=GROUP, message="x")
    exchange.send(conn_id="c1", topic="other.topic", group=GROUP, message="x")
    exchange.send(conn_id="c1", topic=TOPIC, group="other-group", message="x")

    result = exchange.get_inbox("c1")
    assert not isinstance(result, InboxClosed)
    assert isinstance(result, Inbox)
    assert result.queue.qsize() == 0


@pytest.mark.asyncio
async def test_send_full_inbox_kicks_the_connection():
    exchange, inbox = make_exchange_with_inbox(grace_s=0.0)
    label = {"topic": TOPIC, "type": "anonymous"}
    before = REGISTRY.get_sample_value("firehose_kicked_total", label) or 0

    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message=str(i))
    # one message beyond capacity kicks
    exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message="over")

    after = REGISTRY.get_sample_value("firehose_kicked_total", label) or 0

    assert inbox.kicked is True
    assert inbox.kick.is_set()
    assert inbox.queue.qsize() == QUEUE_MAX_SIZE
    assert isinstance(exchange.get_inbox("c1"), InboxClosed)
    assert exchange.get_subscribers(topic=TOPIC, group=GROUP) == []
    assert after == before + 1


@pytest.mark.asyncio
async def test_send_within_grace_drops_instead_of_kicking():
    exchange, inbox = make_exchange_with_inbox()
    label = {"topic": TOPIC, "type": "anonymous"}
    before = REGISTRY.get_sample_value("firehose_kicked_total", label) or 0

    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message=str(i))
    # full inbox inside the grace window: the message is dropped, the
    # ramping connection survives
    exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message="over")

    after = REGISTRY.get_sample_value("firehose_kicked_total", label) or 0

    assert inbox.kicked is False
    assert not inbox.kick.is_set()
    assert inbox.queue.qsize() == QUEUE_MAX_SIZE
    assert exchange.get_subscribers(topic=TOPIC, group=GROUP) == ["c1"]
    assert after == before


@pytest.mark.asyncio
async def test_send_within_grace_counts_the_dropped_message():
    exchange, inbox = make_exchange_with_inbox()
    label = {"topic": TOPIC, "type": "anonymous"}
    before = REGISTRY.get_sample_value("firehose_dropped_total", label) or 0

    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message=str(i))
    exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message="over")

    after = REGISTRY.get_sample_value("firehose_dropped_total", label) or 0

    # the grace keeps the connection but silently loses the message:
    # the loss must be observable
    assert inbox.kicked is False
    assert after == before + 1


@pytest.mark.asyncio
async def test_kicking_does_not_count_as_a_grace_drop():
    exchange, inbox = make_exchange_with_inbox(grace_s=0.0)
    label = {"topic": TOPIC, "type": "anonymous"}
    before = REGISTRY.get_sample_value("firehose_dropped_total", label) or 0

    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message=str(i))
    # past the grace the full inbox is kicked, not grace-dropped
    exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message="over")

    after = REGISTRY.get_sample_value("firehose_dropped_total", label) or 0

    assert inbox.kicked is True
    assert after == before


@pytest.mark.asyncio
async def test_get_message_returns_messages_then_inbox_closed():
    exchange, inbox = make_exchange_with_inbox(grace_s=0.0)
    exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message="a")
    exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message="b")

    assert await inbox.get_message() == "a"

    # drain one slot, then overflow: the kick wakes the parked getter
    assert await inbox.get_message() == "b"
    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message=str(i))
    exchange.send(conn_id="c1", topic=TOPIC, group=GROUP, message="over")

    result = await asyncio.wait_for(inbox.get_message(), timeout=2)
    assert isinstance(result, InboxClosed)
    assert "too slow" in str(result)


@pytest.mark.asyncio
async def test_send_or_wait_kicks_when_others_subscribed():
    exchange = Exchange(grace_s=0.0)
    exchange.subscribe(topic=TOPIC, group=GROUP, conn_id="a", user=ANONYMOUS)
    exchange.subscribe(topic=TOPIC, group=GROUP, conn_id="b", user=ANONYMOUS)
    inbox_a = exchange.get_inbox("a")
    inbox_b = exchange.get_inbox("b")
    assert isinstance(inbox_a, Inbox)
    assert isinstance(inbox_b, Inbox)

    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="a", topic=TOPIC, group=GROUP, message=str(i))

    # a full inbox with company is kicked immediately, no waiting
    await asyncio.wait_for(
        exchange.send_or_wait(conn_id="a", topic=TOPIC, group=GROUP, message="over"),
        timeout=1,
    )

    assert inbox_a.kicked is True
    assert inbox_b.kicked is False


@pytest.mark.asyncio
async def test_send_or_wait_within_grace_drops_instead_of_kicking():
    exchange = Exchange()
    exchange.subscribe(topic=TOPIC, group=GROUP, conn_id="a", user=ANONYMOUS)
    exchange.subscribe(topic=TOPIC, group=GROUP, conn_id="b", user=ANONYMOUS)
    inbox_a = exchange.get_inbox("a")
    inbox_b = exchange.get_inbox("b")
    assert isinstance(inbox_a, Inbox)
    assert isinstance(inbox_b, Inbox)

    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="a", topic=TOPIC, group=GROUP, message=str(i))

    # inside the grace the pump does not wait on a ramping inbox and
    # does not kick: the message is dropped, the group keeps streaming
    await asyncio.wait_for(
        exchange.send_or_wait(conn_id="a", topic=TOPIC, group=GROUP, message="over"),
        timeout=1,
    )

    assert inbox_a.kicked is False
    assert inbox_b.kicked is False
    assert inbox_a.queue.qsize() == QUEUE_MAX_SIZE
    assert exchange.get_subscribers(topic=TOPIC, group=GROUP) == ["a", "b"]


@pytest.mark.asyncio
async def test_send_or_wait_within_grace_counts_the_dropped_message():
    exchange = Exchange()
    exchange.subscribe(topic=TOPIC, group=GROUP, conn_id="a", user=ANONYMOUS)
    exchange.subscribe(topic=TOPIC, group=GROUP, conn_id="b", user=ANONYMOUS)
    inbox_a = exchange.get_inbox("a")
    assert isinstance(inbox_a, Inbox)
    label = {"topic": TOPIC, "type": "anonymous"}
    before = REGISTRY.get_sample_value("firehose_dropped_total", label) or 0

    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="a", topic=TOPIC, group=GROUP, message=str(i))
    await asyncio.wait_for(
        exchange.send_or_wait(conn_id="a", topic=TOPIC, group=GROUP, message="over"),
        timeout=1,
    )

    after = REGISTRY.get_sample_value("firehose_dropped_total", label) or 0

    assert inbox_a.kicked is False
    assert after == before + 1


@pytest.mark.asyncio
async def test_send_or_wait_last_subscriber_waits_then_delivers():
    exchange = Exchange()
    exchange.subscribe(topic=TOPIC, group=GROUP, conn_id="solo", user=ANONYMOUS)
    inbox = exchange.get_inbox("solo")
    assert isinstance(inbox, Inbox)

    for i in range(QUEUE_MAX_SIZE):
        exchange.send(conn_id="solo", topic=TOPIC, group=GROUP, message=str(i))

    task = asyncio.create_task(
        exchange.send_or_wait(conn_id="solo", topic=TOPIC, group=GROUP, message="held")
    )
    await asyncio.sleep(0.1)
    # the sole subscriber is never kicked; the pump waits
    assert not task.done()
    assert inbox.kicked is False

    # once the client drains, the held message is delivered in order
    inbox.queue.get_nowait()
    await asyncio.wait_for(task, timeout=2)
    assert inbox.queue.qsize() == QUEUE_MAX_SIZE
    held = [inbox.queue.get_nowait() for _ in range(QUEUE_MAX_SIZE)]
    assert held[-1] == "held"


def test_unsubscribe_removes_the_inbox():
    exchange, _ = make_exchange_with_inbox()

    exchange.unsubscribe("c1")
    exchange.unsubscribe(None)

    assert exchange.get_inbox("c1") is None or isinstance(
        exchange.get_inbox("c1"), InboxClosed
    )
    assert exchange.get_subscribers(topic=TOPIC, group=GROUP) == []


def test_kick_constants_are_the_websocket_close_policy():
    # 1013 = try again later: the client was too slow
    assert KICK_CODE == 1013
    assert KICK_REASON == "inbox full"
    # F2 join grace: ramping joiners cannot be kicked for 30s, and the
    # inbox absorbs ~5s of backlog at 200/s before dropping
    assert GRACE_S == 30.0
    assert QUEUE_MAX_SIZE == 1000
    # the grace is configurable; the constant is the settings default
    from bot_detector.firehose.core.config import Settings

    assert Settings().kick_grace_s == GRACE_S


@pytest.mark.asyncio
async def test_get_message_prefers_queued_message_over_stale_receive_task():
    """A completed long-lived receive task may hold a stale ASGI event
    (e.g. the handshake 'websocket.connect'); the queued message must
    win, otherwise it is silently discarded."""
    exchange, inbox = make_exchange_with_inbox()

    async def stale_receive() -> dict:
        return {"type": "websocket.connect"}

    disconnect = asyncio.create_task(stale_receive())
    await asyncio.sleep(0)  # let the receive task complete
    assert disconnect.done()

    inbox.queue.put_nowait("hello")
    result = await asyncio.wait_for(inbox.get_message(disconnect=disconnect), timeout=2)

    assert result == "hello"
    # the stale event is still delivered on the next call, so the
    # route can end the loop on a real disconnect
    second = await asyncio.wait_for(inbox.get_message(disconnect=disconnect), timeout=2)
    assert second == {"type": "websocket.connect"}
