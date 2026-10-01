# firehose container smoke test

Real-stack check: the firehose container, real kafka, real uvicorn,
real websockets. DST cannot see this layer by design.

Run from the repo root:

```sh
make smoke-firehose
```

The target starts kafka + mysql + the seeder (fresh 1000-message
`players.scraped` seed) + the firehose, then runs the smoke runner
container and tears everything down. Exit 0 means every check passed.

## What is checked

1. the websocket endpoint answers
2. two fast clients each receive exactly the seeded count, with
   byte-identical sequences (one pump, one order, fanout parity)
3. a slow client (5ms per message) receives the full seeded stream and
   is never kicked
4. the runner then produces a 10k-message burst; the stalled client
   (connects, never reads) has its inbox overflow past the kick grace
   and gets kicked - the server-side `firehose_kicked_total` counter is
   the authoritative signal, since a client that never reads cannot see
   its own 1013 close frame (it observes an abnormal 1006 close)
5. after all disconnects, `firehose_connections` returns to 0

## Knobs (env)

`WS_URL`, `METRICS_URL`, `KAFKA_BROKER`, `EXPECTED_MESSAGES` (seed
size), `BURST_MESSAGES` (default 10000 - the burst must exceed TCP
autotuned socket buffers, ~10MB, or the stalled client never backs up
and the kick never fires), `START_TIMEOUT_S`, `IDLE_TIMEOUT_S`,
`KICK_WAIT_S`.

The smoke profile overrides two product settings: `RESET_TOPICS=true`
(fresh seed every run) and `KICK_GRACE_S=5` (fast kicks).
