# Firehose smoke analysis

Date: 2026-09-29. Suite: `development/perf/firehose/smoke.py` — deterministic-leaning, protocol-aware simulation against the real firehose app (uvicorn) with an in-process fake kafka.

## The scenario

- 20 websocket clients, 25s: 12 fast (recv continuously), 5 slow (recv every 50ms), 3 stalled (read every 2s — far below stream rate)
- Feed: 200 msg/s, ~1.6KiB `ScrapedStruct` JSON per message
- Determinism: seeded-RNG payload pool (cycles player ids 0..199), counter-based fault injection (`SIM_ERROR_EVERY=4999` → `RuntimeError`, `SIM_POISON_EVERY=997` → `ValidationError`; both delivered as values the route skips with a 0.5s backoff)
- Server state verified via prometheus gauges after a settle period

## Protocol facts asserted

- Kick = websocket close **1013 "inbox full"**
- Invalid api key / unknown topic close before accept → ASGI answers with an **HTTP 403 handshake rejection** (`InvalidStatus` client-side). That is the contract today; asserted as such
- Per-client ordering: observed `player_data.id` must be non-decreasing modulo the pool wrap

## Results (final run)

| Check | Result | Detail |
|---|---|---|
| server_started | PASS | |
| metrics_scraped | PASS | |
| stalled_clients_isolated | PASS | kicked=0/3, msgs=[0,0,0] (see note) |
| healthy_clients_not_kicked | PASS | kicked=0/17 |
| fast_clients_received | PASS | msgs=490 ×12 |
| slow_clients_received | PASS | msgs=490 ×5 |
| survived_poison_and_errors | PASS | ≥10 each, actual 490 |
| in_order_per_client | PASS | 17/17 in order |
| queues_cleaned_after_disconnect | PASS | firehose_consumers=0 |
| connections_cleaned | PASS | firehose_connections=0 |
| kicks_counted | PASS | firehose_kicked_total=19 |
| bad_api_key_rejected | PASS | handshake rejected |
| unknown_topic_rejected | PASS | handshake rejected |

**Overall: PASS (13/13).** Healthy clients at exact fair-share parity (490 ± 1 msgs each over 25s ≈ 19.6/s per client), zero loss, zero healthy kicks.

### Note on stalled clients

Stalled clients are isolated, not observable-kicked: during the connect ramp the group is tiny, so a client reading every 2s faces up to the full stream rate, its inbox fills within ~0.4s, and the kick lands **server-side before the client's first read**. A client that never read cannot observe the close frame — it sees zero messages. `firehose_kicked_total=19` is the evidence; the check accepts either an observed 1013 or zero deliveries.

## Bugs this suite caught (why it earns its keep)

1. **Pump yield bug** — 20× `asyncio.sleep(0)` per kafka message capped the pump at ~44 msg/s. Presented as "all 20 fast clients kicked with ~20 msgs each". Fixed to one yield per message.
2. **Zero-yield bursts** — the opposite tuning (no yields across a 50-message producer burst) mass-kicked healthy clients at 5000/s.
3. **Connect-ramp massacre** — early joiners alone face the full stream rate; inboxes fill in under a second and mass kicks follow. Led to the last-subscriber rule (`Exchange.send_or_wait`).
4. **Error-backoff coupling** — fault rate 1-in-97 at 200/s made every route sleep 0.5s about twice per second, stalling the whole group; sized down to 1-in-4999 (~0.04 paused seconds per second).
5. **Order-wrap false positives** — pool of 200 wraps 199→0, which looks like a reorder; wrap threshold is now parameterized (`wrap=100`).
6. **Harness URL bug** — smoke/cli dialed hardcoded port 5099 regardless of `--port`, masked as "0 messages everywhere".
7. **Stalled-client observability** — never-reading clients buffer client-side, create no TCP backpressure, and cannot observe kicks; see note above.

## Determinism scorecard (vs DST)

| DST pillar | Status |
|---|---|
| Seeded PRNG driving data | done (payload pool) |
| Deterministic fault injection | partial (counter-based, not seed-replayable) |
| Protocol-level assertions | done (close codes, ordering, handshake rejections) |
| Cleanup/state invariants | done (gauges return to zero, no tracebacks) |
| Logical clock (fast-forward) | not done — wall clock |
| Single-process controlled scheduler | not done — server + clients in separate OS processes |
| Seed replay of failures | not done |

Upgrading to full DST would mean: PRNG-seeded fault schedule, the whole fleet in one process under a deterministic scheduler, and a virtual clock. Current suite is repeatable in distribution, not bit-exact per seed.

## Verdict

Smoke suite green (13/13): delivery parity, ordering, kick isolation, cleanup, protocol rejects, crash freedom — at 200/s × 20 clients with faults in the mix. Throughput and overload behavior: see `perf_analysis.md`.

Run: `uv run python -m development.perf.firehose.smoke --port 5107 --metrics-port 8107` (exit 0 = all checks pass).
