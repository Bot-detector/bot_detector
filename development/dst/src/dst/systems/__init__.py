"""Simulated external systems for DST scenarios.

Each system is a duck-typed stand-in for a real integration, running
on the virtual clock and paying VirtualMachine costs for its work.
Faults (transport, protocol, application level) are seeded and
returned as values so scenarios replay deterministically.
"""

from .fake_firehose_clients import (
    ClientReport,
    CloseFrame,
    FirehoseClient,
    FirehoseClientConfig,
    FirehoseFleet,
    FirehoseHub,
    FirehoseHubConfig,
)
from .fake_kafka import (
    FakeKafka,
    FakeKafkaError,
    KafkaConfig,
    KafkaFaults,
    KafkaMessage,
)

__all__ = [
    "ClientReport",
    "CloseFrame",
    "FakeKafka",
    "FakeKafkaError",
    "FirehoseClient",
    "FirehoseClientConfig",
    "FirehoseFleet",
    "FirehoseHub",
    "FirehoseHubConfig",
    "KafkaConfig",
    "KafkaFaults",
    "KafkaMessage",
]
