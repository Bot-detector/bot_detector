# Firehose performance analysis

Date: 2026-09-29

Scope: `bases/bot_detector/firehose/` (spec: `spec_firehose_v2.md`) under websocket load.
Harness: this directory (`sim_server.py` runs the real app against an in-process fake kafka
feeding ~1.6 KiB ScrapedStruct JSON at `SIM_RATE_S`; `clients.py` runs fast/slow/stalled
websocket clients). All runs: single host, single event loop for the server, 20 clients,
25 s duration unless noted.

## Scenarios

| Scenario  | Rate   | Delivered | Agg throughput | Kicked | Survivor(s)                                   | p99 gap        |
|-----------|--------|-----------|----------------|--------|-----------------------------------------------|----------------|
| baseline  | 500/s  | 86,463    | 3,458/s        | 13/20  | 7 x ~11,715 msgs (~469/s each)                | ~7.7 ms (fast) |
| throughput| 2000/s | 47,657    | 1,906/s        | 19/20  | 1 x 47,220 msgs (~1,889/s solo)               | 3.5-7.2 ms     |
| errors    | 500/s  | 15,300    | 612/s          | 19/20  | 1 x 11,275 msgs (~451/s solo)                 | 6.0-11.6 ms    |
| mixed     | 500/s  | 2,839     | ~114/s         | 17/20  | 3 stalled, 0 msgs                             | ~51.4 ms       |
| smoke     | 200/s  | 8,311     | ~332/s         | 0/17 healthy | 17 healthy, 488-489 msgs each (~19.6/s) | ~52.1 ms       |

Details:

- baseline (500/s): each of the 13 kicked clients received exactly 343 msgs before
  close 1013 "inbox full"; the 7 survivors split the rest evenly (6 x 11,715 + 1 x 11,714),
  ~468.6/s per client.
- throughput (2000/s): the 19 kicked clients received exactly 23 msgs each; one survivor
  absorbed 47,220 msgs (1,888.8/s) with p50 gap 0.19 ms.
- errors (500/s, faults on: `--error-pct 0.02 --poison-pct 0.1`, matching the original
  `SIM_ERROR_EVERY=4997` / `SIM_POISON_EVERY=997` rates): kicked clients received
  209-212 msgs; sole survivor 11,275 msgs, p99 gap 11.6 ms.
- mixed (500/s, 12 fast / 5 slow@50 ms / 3 stalled): healthy clients show exact parity
  (167 msgs each, p50 gap ~50.6 ms, p99 ~51.4 ms); stalled clients received 0 msgs.
- smoke (200/s, 12 fast / 5 slow@50 ms / 3 stalled, errors+poison on): zero healthy kicks,
  488-489 msgs per healthy client, `in_order` 17/17.

## Findings

### F1 - Pump yield economics

The pump issued 20 `asyncio.sleep(0)` yields per kafka message (one per subscriber). Each
`sleep(0)` costs a full event-loop cycle, ~1 ms under uvicorn, so the pump was capped at
~44 msg/s regardless of feed rate. Fixed to a single yield per message. After the fix, the
200/s smoke run shows perfect fair-share parity: 488-489 msgs per healthy client, zero
loss, `in_order` 17/17.

### F2 - Connect-ramp massacre

Clients connect over ~1-2 s. Early joiners alone face the full stream rate (500/s solo),
their `inbox(100)` fills in under a second, and they are kicked as later joiners arrive.
Server logs show 19-20 kicks within seconds of start in every >=500/s run (baseline,
throughput, errors, mixed). Root cause: no admission pacing; the kick policy is
rate-sensitive only through `inbox(100)`.

### F3 - Last-subscriber rule

`Exchange.send_or_wait` (implemented today): the sole subscriber is never kicked for
backpressure; the pump waits and kafka retains. Observed effect: converts mass death into
survivor-take-all. In the 2000/s scenario one client absorbed 1,889/s solo. The rule also
protects joiner #1 during the connect ramp, but only while the group size is 1.

### F4 - Overload behavior is spec-conformant

Beyond loop capacity, mass kicks happen and the fastest client(s) survive and determine
aggregate throughput. Spec: "fast clients determine throughput; slow clients get kicked."
Throughput scenario: 19 kicked, 1 survivor at 1,889/s. Baseline: 13 kicked, 7 survivors
splitting ~470/s each.

### F5 - Stalled-client observability

A never-reading websocket client does not create TCP backpressure (the websockets library
buffers client-side), so the kick is only observable server-side via
`firehose_kicked_total`. In the smoke run the 3 stalled clients recorded
`close_code=None` and 0 msgs: a client kicked before its first read sees zero messages and
cannot observe the close frame. Slow-read (2 s interval) stalled clients in the mixed run
were isolated during the ramp with 0 msgs delivered.

### F6 - Error-backoff coupling

Every Exception value fans out to ALL inboxes, and the route sleeps 0.5 s per error. A
group-wide pause therefore costs `error_rate x 0.5s`. Sizing rule for the sim: keep
`error_rate x 0.5s` well below inflow (smoke uses `error_pct=0.02` at 200/s, ~0.04
error/s). The errors scenario (`error_pct=0.02` at 500/s, ~0.1 error/s) measured 612/s
aggregate vs 3,458/s clean, but the ramp massacre (19/20 kicked) confounds the
comparison; treat it as an upper bound of degradation.

### F7 - Open anomaly: baseline kick at parity

Baseline (500/s) mass-kicked 13 clients that had received near-parity (~343 msgs each).
The exact kick trigger at that instant is unknown: kick timestamps and per-inbox queue
depth at kick are not logged. Needs instrumentation. Listed as next step.

## Capacity summary

- Sustainable fair-share operation: 200/s x 20 subscribers (~19.6/s per client, 51 ms p50
  gap) - smoke run.
- 500/s works for survivors post-ramp (~470/s each across 7 clients).
- 2000/s works for a single survivor (~1,889/s).
- Loop-turn economics (~4-5 event-loop turns per delivered message) are the binding
  constraint, not bandwidth or serialization.

## Recommendations

1. Join grace/pacing for new subscribers (e.g. ramp the per-inbox fill rate, or delay
   kicks for the first N seconds of a connection) to kill the ramp massacre (F2).
2. Log kick timestamps and inbox depth at kick (F7).
3. Consider a per-inbox token bucket if parity under burst matters.
4. Keep the last-subscriber rule (F3); it degrades gracefully and matches kafka retention.

## Limitations

- Single host; client and server share CPU.
- Single event loop for the server.
- Fake kafka: no broker, no network hop.
- Synthetic ~1.6 KiB payloads from a pre-generated pool.

## Reproducing

No README in this directory; raw commands (repo root):

```sh
# baseline
uv run python -m development.perf.firehose run --n 20 --duration 25 --rate 500 \
    --port 5110 --metrics-port 8110 --verbose

# throughput
uv run python -m development.perf.firehose run --n 20 --duration 25 --rate 2000 \
    --port 5110 --metrics-port 8110 --verbose

# errors (seeded, pct-based fault injection; replays with the same seed)
uv run python -m development.perf.firehose run --n 20 --duration 25 --rate 500 \
    --seed 0 --error-pct 0.02 --poison-pct 0.1 \
    --port 5110 --metrics-port 8110 --verbose

# mixed (serve in one shell, clients in another)
uv run python -m development.perf.firehose serve --rate 500 --port 5110 --metrics-port 8110
uv run python -m development.perf.firehose clients --n 20 --duration 25 --slow-ms 50 \
    --mix fast,fast,fast,fast,fast,fast,fast,fast,fast,fast,fast,fast,slow,slow,slow,slow,slow,stalled,stalled,stalled \
    --url ws://127.0.0.1:5110/firehose/players.scraped?anonymous=1

# smoke (functional suite)
uv run python -m development.perf.firehose.smoke
```

For the functional smoke suite (handshake rejection, poison handling, cleanup metrics),
see `smoke_analysis.md` in this directory.
