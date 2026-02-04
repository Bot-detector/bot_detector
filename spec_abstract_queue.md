# Abstract Queue Specification

## Context

Design a generic queue component abstraction where Kafka is the primary implementation. The goal is to provide a type-safe, async queue interface that can support multiple backends (Kafka, RabbitMQ, Redis streams) while preserving the proven patterns from the existing Kafka implementation.

## Requirements

- **Generic type-safe queue interface** with Pydantic validation at message boundaries
- **Async operations** for non-blocking I/O throughout produce/consume cycles
- **Batch processing support** with configurable size (max_records) and timing (timeout_ms)

## Design Principles

- **Feature-based pattern**: Simple wrapper classes that configure topic, backend, and validation rules - no custom logic in feature queues
- **Implementation-agnostic core**: Generic `Queue[T]` defines the contract, backends extend via extension points rather than overriding core methods
- **Preserve retry patterns**: Exponential backoff for transient failures (KafkaTimeoutError) and re-produce on consumer errors
- **Minimal interface**: `get`, `get_many`, `put`, `put_many` with lifecycle management - no additional abstraction layers

## Key Patterns

### Type Safety
Generic `T` bound to `BaseModel` for runtime validation via Pydantic. Type checking happens at message boundaries, not in transit.

### Error Separation
Return errors as values

### Lifecycle Management
`start()` initializes connections and resources; `stop()` performs async cleanup. Critical for AIOKafkaConsumer/Producer which require proper shutdown to avoid resource leaks.

### Batch Processing
`get_many(max_records, timeout_ms)` accumulates messages in a buffer until count or timeout reached. Batcher class manages accumulation logic - consumers don't implement batching themselves.

### Retry Pattern
Exponential backoff for transient failures with configurable max backoff (60s default). Producers retry indefinitely; consumers re-produce failed batches before sleep. This prevents data loss during outages.

## Pseudo Code Examples

```python
# Type-safe generic interface
class Queue[T: BaseModel, Protocol]:
    async def start(self)-> None: ...
    async def stop(self)-> None: ...
    async def get(self) -> tuple[Optional[T], Optional[str]]: ...
    async def get_many(self, max_records: int, timeout_ms: int) -> tuple[list[T], list[str]]: ...
    async def put(self, data: T, topic: str = "default") -> None: ...
    async def put_many(self, data: list[T], topic: str = "default")-> None: ...
```

```python
# Feature-based implementation - no custom logic
class PlayersScrapedQueue(Queue[ScrapedStruct]):
    def __init__(self, backend: str = "kafka"):
        self.topic = "players.scraped"
        self._backend = backend
```

```python
# Usage pattern with batch processing
queue = PlayersScrapedQueue()
await queue.start()
batch, errors = await queue.get_many(max_records=100, timeout_ms=5000)
await asyncio.gather(*(process(item) for item in batch))
```

## Extension Points

- **Backend-specific features**: Lag monitoring for Kafka consumers, routing keys for RabbitMQ, consumer groups for message distribution
- **Serialization per-backend**: JSON (orjson) for Kafka, AMQP for RabbitMQ, pickled bytes for Redis streams
- **Consumer groups and partitioning**: Backend handles partition assignment logic; callers pass partition_key hints for routing
