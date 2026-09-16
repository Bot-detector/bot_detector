from prometheus_client import Counter, Histogram

BATCHES_CONSUMED = Counter(
    name="worker_batches_consumed",
    documentation="Batches consumed from the queue by WorkerRunner",
    labelnames=["worker"],
)

MESSAGES_CONSUMED = Counter(
    name="worker_messages_consumed",
    documentation="Messages consumed from the queue by WorkerRunner",
    labelnames=["worker"],
)

MESSAGES_REQUEUED = Counter(
    name="worker_messages_requeued",
    documentation="Messages requeued after failed or partial handling",
    labelnames=["worker"],
)

ERRORS = Counter(
    name="worker_errors",
    documentation="Errors encountered by WorkerRunner",
    labelnames=["worker", "kind"],
)

HANDLE_LATENCY = Histogram(
    name="worker_handle_seconds",
    documentation="Time spent in Worker.handle()",
    labelnames=["worker"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
