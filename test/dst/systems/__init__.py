"""Simulated external systems for DST scenarios.

Each system is a duck-typed stand-in for a real integration, running
on the virtual clock and paying Machine costs for its work.
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
from .seed import hiscores, players, reports
from .sim_broker import SimBroker, SimBrokerConfig, SimMessage
from .sim_db import SimDB, TableSchema

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
    "SimBroker",
    "SimBrokerConfig",
    "SimDB",
    "SimMessage",
    "TableSchema",
    "hiscores",
    "players",
    "reports",
]
