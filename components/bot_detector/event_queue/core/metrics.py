from prometheus_client import Counter, Histogram

MESSAGES_PRODUCED = Counter(
    name="event_queue_messages_produced",
    documentation="Messages successfully produced to the event queue",
    labelnames=["queue"],
)

MESSAGES_CONSUMED = Counter(
    name="event_queue_messages_consumed",
    documentation="Messages successfully consumed from the event queue",
    labelnames=["queue"],
)

GET_LATENCY = Histogram(
    name="event_queue_get_seconds",
    documentation="Latency of event queue get_one/get_many calls",
    labelnames=["queue", "op"],
    buckets=(
        0.0005,
        0.001,
        0.0025,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)
