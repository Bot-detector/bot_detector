# worker_report

Consumes report messages from the `reports.to_insert` Kafka topic, transforms them, and inserts them into the database as batched detections.

## Architecture

```
┌─────────────┐
│   main.py   │  wiring & lifecycle
├─────────────┤
│  settings.py│  pydantic-settings (N_WORKERS, MAX_BATCH_SIZE, MAX_INTERVAL_MS)
├─────────────┤
│  worker.py  │  ReportWorker.handle() + insert_batch()
├─────────────┤
│ adapter.py  │  transform_report() — struct-to-struct
└─────────────┘
```

### Dependency flow

```
main.py
  → worker component (WorkerRunner)
  → database component (ReportRepo, session factory)
  → event_queue component (KafkaConfig, ReportsToInsertStruct)
  → structs component (ParsedDetection)
```

## Flow

1. `main()` creates `N_WORKERS` instances of `ReportWorker`, each wired to a `WorkerRunner`.
2. Each `WorkerRunner` creates a Kafka queue (consumer + producer), starts it, and enters the consume loop.
3. On each iteration, `WorkerRunner` fetches a batch of `ReportsToInsertStruct` messages from Kafka.
4. `ReportWorker.handle()` transforms each record via `adapter.transform_report()` (filters out unsupported versions), then calls `insert_batch()`.
5. `insert_batch()` writes the parsed detections to MySQL in a single transaction.
6. On success, `WorkerRunner` commits the Kafka offset.
7. On failure (e.g. `OperationalError`), `WorkerRunner` requeues the batch and retries.

## Sequence diagram

```mermaid
sequenceDiagram
    participant M as main.py
    participant WR as WorkerRunner
    participant K as Kafka
    participant W as ReportWorker
    participant A as adapter.py
    participant DB as MySQL

    M->>WR: runner.run() (per worker)
    WR->>K: queue.start()
    loop until stop_event
        WR->>K: get_many(batch_size)
        K-->>WR: ReportsToInsertStruct[]
        WR->>W: handle(batch)
        loop each record
            W->>A: transform_report(record)
            A-->>W: ParsedDetection | None
        end
        alt has valid detections
            W->>DB: insert_batch(parsed)
            DB-->>W: ok
            W-->>WR: return
            WR->>K: commit()
        else DB error
            W-->>WR: raise OperationalError
            WR->>K: requeue(batch)
            WR->>K: commit()
        else no valid records
            W-->>WR: return (no-op)
            WR->>K: commit()
        end
    end
    WR->>K: queue.stop()
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `N_WORKERS` | `1` | Number of parallel worker instances |
| `MAX_BATCH_SIZE` | `10_000` | Max messages fetched per consume iteration |
| `MAX_INTERVAL_MS` | `1_000` | Kafka consumer timeout in milliseconds |
