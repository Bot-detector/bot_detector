# firehose

Streams kafka messages over a websocket. One shared kafka consumer per topic and consumer group, fanned out to websocket clients.

## Architecture

Two sections, separated by `asyncio.Queue` handoffs. The kafka section only knows queues; the websocket section only knows queues and sockets.

```mermaid
flowchart TB
    subgraph KAFKA["Kafka section (upstream, pull)"]
        direction TB
        KT[("kafka topics<br>players.scraped<br>reports.to_insert")]
        QR["QueueRepo<br>resolve_consumer_group<br>create_consumer"]
        CMGR["ConsumerManager<br>refcounted exchange per (topic, group)"]
        CONSUME["Exchange._consume<br>serialize once per message"]
        HOLD["DelayedExchange._hold<br>hold reports 2h<br>(reports.to_insert)"]
        DELIVER["Exchange._deliver"]
        INBOX["inbox per connection<br>registry keyed by conn_id<br>queue(100), kick flag"]

        KT --> QR --> CMGR --> CONSUME --> HOLD --> DELIVER --> INBOX
    end

    subgraph WS["WebSocket section (downstream, push)"]
        direction TB
        ROUTE["ws /firehose/{topic}<br>loop: inbox.queue.get vs<br>kick vs websocket.receive"]
        CONNM["ConnectionManager<br>the only socket interface:<br>connect / send(2s) / close"]
        CLIENTS["websocket clients"]

        ROUTE --> CONNM --> CLIENTS
        INBOX --> ROUTE
    end
```

- every connection gets an inbox under its `conn_id`; the route fetches it via `exchange.get_inbox(conn_id)` and delivers each message through `ConnectionManager.send` (bounded, close on timeout)
- the exchange never touches sockets: a full inbox just sets the kick flag; the route closes the socket and unsubscribes

### Backpressure and lifecycle

- First subscriber: `ConsumerManager.create` builds, registers and starts the exchange; `get` refcounts +1.
- Last subscriber leaves: `ConsumerManager.release` drops the refcount, `delete` stops and unregisters the exchange (consumer_manager.py).
- Slow client: a full inbox (100) sets the kick flag; the route closes the websocket (1013) and unsubscribes; the others keep streaming (`firehose_kicked_total`).
- Failing or too-slow send: the route closes the connection the same way (a cancelled send can leave a partial frame; never retry).
- No subscribers left: the consume loop stops; kafka retains the stream until a client connects.
- Two tabs on one user group: each gets a copy (fan-out per connection).

## Dependency flow

```mermaid
flowchart LR
    subgraph BASE["base: bot_detector/firehose"]
        API["api/ (routes)"]
        APP["app/ (wiring, managers, exchanges)"]
        CORE["core/ (config, server)"]
    end

    EQ["component: event_queue<br>(kafka adapter + factory)"]
    DB["component: database<br>(auth session factory)"]
    LOG["component: logfmt"]

    CORE --> API
    CORE --> APP
    APP --> EQ
    APP --> DB
    CORE --> LOG
```

Deployed by `projects/firehose`.

## Endpoints

| Endpoint | Type | Auth | Description |
|---|---|---|---|
| `/firehose/{topic}` | websocket | api key, `?token=`, or anonymous | Stream a topic |
| `/firehose/topics` | GET | none | List allowed topics |
| `/me` | GET | api key / discord | Caller identity |

Topics: `players.scraped` (live), `reports.to_insert` (delayed 2h by `DelayedExchange`).
