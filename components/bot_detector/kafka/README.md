# Kafka Feature-Based Pattern

## Overview

Kafka producers and consumers follow a feature-based pattern where each topic has its own directory containing:
- `consumer.py` - Typed consumer using `BaseConsumer[T]`
- `producer.py` - Typed producer using `BaseProducer[T]`
- `struct.py` - Pydantic struct for message validation
- `__init__.py` - Exports for public API

## Creating a New Kafka Topic

1. Create a new directory under `components/bot_detector/kafka/[feature_name]/`
2. Add `consumer.py` extending `BaseConsumer[YourStruct]`
3. Add `producer.py` extending `BaseProducer[YourStruct]`
4. Add `struct.py` with your Pydantic struct
5. Add `__init__.py` exporting consumer, producer, and struct
6. Add unit tests in `test/components/bot_detector/kafka/test_[feature_name].py`

## Usage Example

```python
from bot_detector.kafka.[feature_name] import [FeatureName]Consumer, [FeatureName]Producer

# Consumer
consumer = [FeatureName]Consumer(
    group_id="my-group",
    bootstrap_servers="localhost:9092",
)
await consumer.start()
messages, errors = await consumer.consume_many(max_records=100, timeout_ms=1000)

# Producer
producer = [FeatureName]Producer(
    bootstrap_servers="localhost:9092",
)
await producer.start()
await producer.produce_one(message, partition_key=b'key')
```

## Important Notes

- Keep consumer/producer implementations simple - no custom logic in producer/consumer
- Use `BaseConsumer.consume_many()` for batching (no custom `buffer_records()`)
- Use `BaseConsumer.commit()` for committing offsets (no custom `commit()`)
- Retry logic is handled by `BaseProducer` (no custom retry loops)
- Partition key generation should be handled by callers, not producers
