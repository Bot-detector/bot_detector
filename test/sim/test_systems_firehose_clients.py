"""Fake firehose clients: fanout parity, grace drops, kicks, ordering."""

import asyncio

import pytest

import dst as dst
from dst import VirtualClock
from dst.systems import (
    CloseFrame,
    FirehoseClient,
    FirehoseClientConfig,
    FirehoseFleet,
    FirehoseHub,
    FirehoseHubConfig,
)

PAYLOAD = b"msg"


def drain(client: FirehoseClient, n: int) -> list[bytes | CloseFrame]:
    async def scenario() -> list[bytes | CloseFrame]:
        return [await client.receive() for _ in range(n)]

    return dst.run(scenario()).value


def test_fanout_parity_and_ordering():
    async def scenario() -> list[list[bytes | CloseFrame]]:
        hub = FirehoseHub(FirehoseHubConfig())
        fleet = FirehoseFleet(hub)
        clients = fleet.spawn(3)
        for i in range(10):
            await hub.send_all(f"m{i}".encode())
        return [[await client.receive() for _ in range(10)] for client in clients]

    result = dst.run(scenario())
    a, b, c = result.value
    assert a == b == c == [f"m{i}".encode() for i in range(10)]


def test_slow_client_inside_grace_drops_but_is_not_kicked():
    async def scenario() -> tuple[int, int, list[bytes | CloseFrame], int | None]:
        hub = FirehoseHub(FirehoseHubConfig(kick_grace_s=10.0))
        fast = hub.connect("fast", FirehoseClientConfig(buffer_size=1000))
        hub.connect("slow", FirehoseClientConfig(buffer_size=20))  # never drains
        for i in range(100):
            await hub.send_all(f"m{i}".encode())  # all inside the grace window
        fast_msgs = [await fast.receive() for _ in range(100)]
        report = {r.name: r for r in hub.report()}
        return hub.dropped_total, hub.kicked_total, fast_msgs, report["slow"].close_code

    result = dst.run(scenario())
    dropped, kicked, fast_msgs, slow_close = result.value
    assert kicked == 0
    assert dropped == 80  # slow inbox: 20 buffered, 80 grace drops (counted)
    assert fast_msgs == [f"m{i}".encode() for i in range(100)]  # fast unaffected
    assert slow_close is None


def test_slow_client_past_grace_gets_kicked_with_1013():
    async def scenario() -> tuple[int, int | None, int | None]:
        hub = FirehoseHub(FirehoseHubConfig(kick_grace_s=10.0))
        hub.connect("fast", FirehoseClientConfig(buffer_size=1000))
        hub.connect("slow", FirehoseClientConfig(buffer_size=20))
        for _ in range(40):  # slow inbox: 20 buffered, 20 grace drops
            await hub.send_all(PAYLOAD)
        await asyncio.sleep(11.0)  # slow inbox head ages past the grace window
        await hub.send_all(PAYLOAD)  # full send after grace -> kick
        report = {r.name: r for r in hub.report()}
        return (
            hub.kicked_total,
            report["slow"].close_code,
            report["fast"].close_code,
        )

    result = dst.run(scenario())
    kicked, slow_close, fast_close = result.value
    assert kicked == 1
    assert slow_close == 1013
    assert fast_close is None


def test_kick_wakes_a_parked_receiver():
    async def scenario() -> CloseFrame | bytes:
        hub = FirehoseHub(FirehoseHubConfig(kick_grace_s=1.0))
        client = hub.connect("c0", FirehoseClientConfig(buffer_size=1))
        receive_task = asyncio.create_task(client.receive())  # parked on empty
        await asyncio.sleep(2.0)  # inbox head ages past grace
        await hub.send_all(PAYLOAD)  # full send on the kicked path? no: empty
        hub.disconnect("c0")  # hub closes the connection
        return await receive_task

    result = dst.run(scenario())
    frame = result.value
    assert isinstance(frame, CloseFrame)
    assert frame.code == 1000


def test_client_side_close_surfaces_on_receive():
    async def scenario() -> CloseFrame | bytes:
        hub = FirehoseHub(FirehoseHubConfig())
        client = hub.connect("c0")
        client.close()
        return await client.receive()

    result = dst.run(scenario())
    frame = result.value
    assert isinstance(frame, CloseFrame)
    assert frame.code == 1000


def test_slow_s_paces_receives_in_virtual_time():
    async def scenario() -> tuple[float, int]:
        hub = FirehoseHub(FirehoseHubConfig())
        client = hub.connect("c0", FirehoseClientConfig(buffer_size=100, slow_s=1.0))
        for _ in range(10):
            await hub.send_all(PAYLOAD)
        for _ in range(10):
            await client.receive()
        return hub.clock.time(), client.received_count

    result = dst.run(scenario())
    elapsed, received = result.value
    assert received == 10
    assert elapsed == pytest.approx(10.0)


def test_double_connect_and_unknown_disconnect_rejected():
    hub = FirehoseHub(FirehoseHubConfig(), clock=VirtualClock())
    hub.connect("c0")
    with pytest.raises(ValueError, match="already connected"):
        hub.connect("c0")
    hub.disconnect("c0")
    with pytest.raises(KeyError):
        hub.disconnect("c0")


def test_fleet_spawn_names_and_report():
    hub = FirehoseHub(FirehoseHubConfig(), clock=VirtualClock())
    fleet = FirehoseFleet(hub)
    clients = fleet.spawn(2, prefix="ws")
    assert [c.name for c in clients] == ["ws-0", "ws-1"]
    report = fleet.report()
    assert [r.name for r in report] == ["ws-0", "ws-1"]
    assert all(r.received == 0 and r.close_code is None for r in report)


def test_hub_scenario_replays_deterministically():
    def scenario() -> list[int]:
        async def run() -> tuple[list[int], int, int]:
            hub = FirehoseHub(FirehoseHubConfig(kick_grace_s=5.0))
            fleet = FirehoseFleet(hub)
            slow = fleet.spawn(1, FirehoseClientConfig(buffer_size=10, slow_s=50.0))
            wait = asyncio.create_task(slow[0].receive())
            for i in range(30):
                await hub.send_all(f"m{i}".encode())
            await asyncio.sleep(6.0)
            await hub.send_all(PAYLOAD)
            await wait
            report = fleet.report()
            return (
                [r.received for r in report],
                hub.dropped_total,
                hub.kicked_total,
            )

        return list(dst.run(run()).value)

    assert scenario() == scenario()
