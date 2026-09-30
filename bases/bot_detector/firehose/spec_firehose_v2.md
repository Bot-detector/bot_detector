# Firehose WebSocket v2

## Goal

Consume Kafka messages only while there are connected WebSocket clients and fan them out to every client subscribed to the same consumer group.

A consumer group is an independent firehose subscription:

```text
{topic}:{user}
```

Implemented as (anonymous users share one group; keyed users get `fh-{topic}-{discord_id}`).

## Data flow

```text
Kafka topic
    │
    │  QueueManager: one consumer + pump per (topic, group)
    ▼
Kafka consumer  ── pump: get_one → serialize once → Exchange.send(...)
    │
    ▼
Exchange (global registry, socket-free)
    │  inbox per connection, keyed by conn_id, queue(100)
    │
    ├── Route(conn A) ── inbox.get_message() ──▶ ConnectionManager.send ──▶ WS A
    ├── Route(conn B) ── inbox.get_message() ──▶ ConnectionManager.send ──▶ WS B
    └── Route(conn C) ── inbox.get_message() ──▶ ConnectionManager.send ──▶ WS C
```

## Components and boundaries

| Component | Responsibility | Never does |
|---|---|---|
| `QueueManager` | kafka consumer lifecycle: `create`/`get`/`release`/`delete`, pump task per queue, per-topic holds (e.g. 2h delay) | touch sockets |
| `Exchange` | global inbox registry keyed by `conn_id`: `subscribe`, `get_inbox`, `get_subscribers`, `send`, `unsubscribe` | touch kafka or sockets |
| `ConnectionManager` | the only socket interface: `connect`, `send` (2s bound), `close`, `disconnect`, per-group counts | touch kafka or inboxes |
| route `/firehose/{topic}` | composition: auth → `queue_manager.get` → `connection_manager.connect` → `exchange.subscribe` → drain loop | own queues or registries |

Dependency direction is one-way: `QueueManager → Exchange → (nothing)`. The Exchange never asks the QueueManager; the route is the composition point.

## Kafka semantics

Each subscription has its own Kafka consumer group. The consumer:

* uses `auto.offset.reset=earliest`
* starts from the earliest retained offset when the group has no committed offsets
* consumes only while `exchange.get_subscribers(topic, group)` is non-empty
* stops (queue killed) when the list is empty; Kafka retains the backlog
* resumes when the next client subscribes (dead pumps are revived on acquire)

MVP simplification: offsets are auto-committed (`enable_auto_commit=True`), decoupled from delivery. A crash between poll and delivery can lose messages for the group.

## Client queues

Every connection gets an `Inbox` registered under its `conn_id`:

```python
asyncio.Queue(maxsize=1000)
```

The queue absorbs temporary speed differences between the pump and the client.

## Slow client policy

**Join grace**: for the first 30s after subscribe (`Settings.kick_grace_s`, env
`KICK_GRACE_S`), a full inbox drops
messages instead of kicking - connect ramps fill inboxes while joiners arrive, not
because a client is slow. The pump never waits on a grace-full inbox, so one ramping
client cannot stall the group.

When an inbox reaches 1000 messages past the grace window:

1. The pump is **not** blocked (`Exchange.send` never blocks, never raises).
2. The inbox is kicked: `kicked` flag set, kick event fired, removed from `get_subscribers` (`firehose_kicked_total`, kick log carries `qsize` and subscriber `age_s`).
3. The route sees `InboxClosed("consumed too slow")` from `inbox.get_message()`.
4. The route closes the socket (1013 "inbox full") via the ConnectionManager and unsubscribes.
5. The remaining connections keep streaming.

A failing or too-slow `ConnectionManager.send` (2s bound) closes the socket the same way; a cancelled send can leave a partial frame, so it is never retried.

Fast clients determine throughput; slow clients get dropped.

**Last-subscriber exception**: a full inbox with other subscribers still connected kicks the slow one; the sole subscriber is never kicked for backpressure - the pump waits instead (`Exchange.send_or_wait`). Nobody else is held back, and kafka retains the stream. Within the join grace a multi-subscriber full inbox drops instead of kicking (see above).

## No clients

`exchange.get_subscribers(topic, group) == []` is the single liveness signal:

* the pump stops consuming,
* the last `release()` deletes the queue (registry is the source of truth; no refcounting),
* Kafka remains at the last committed offset,
* the next `subscribe` revives the queue and resumes from that offset.

## Delivery guarantee

Provides:

* Kafka-backed persistence while nobody is connected
* fan-out to all currently subscribed connections
* bounded per-connection buffering (1000)
* slow-client eviction (kick)
* no WebSocket backpressure on Kafka
* ordering preserved within a consumer group

Does **not** provide:

* guaranteed delivery to a WebSocket
* replay after a client disconnects (auto-commit has advanced the group)
* exactly-once WebSocket delivery
* durable per-client offsets

## Example lifecycle

```text
T0  no clients
    Kafka offset = 100, no queue

T1  client A connects
    route: queue_manager.get → consumer + pump start
    exchange.subscribe(conn_a) → inbox

T2  pump: get_subscribers == [conn_a]
    offset 100 → 101 → 102 → ...

T3  client B connects
    same queue, same pump; both inboxes get copies

T4  B stops reading; B's inbox hits 1000 (past the join grace)
    kick: B flagged, removed from get_subscribers

T5  route B: get_message → InboxClosed
    closes B (1013), unsubscribes; A continues: 103, 104, ...

T6  A disconnects
    route A: unsubscribe; release → get_subscribers empty
    pump stops, queue deleted

T7  client C connects
    queue recreated, pump revived, consumes from committed offset
```

## Metrics

* `firehose_consumers{topic,type}` — active kafka queues
* `firehose_connections{topic,type}` — active websockets
* `firehose_messages_total` / `firehose_bytes_total` — delivered payloads
* `firehose_kicked_total` — slow-client evictions

## Core rule

> **Kafka provides the backlog. The QueueManager provides the stream. The Exchange buffers per connection. The route drains. The ConnectionManager talks to sockets. Fast clients determine throughput; slow clients get kicked.**
