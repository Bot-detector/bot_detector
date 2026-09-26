import pytest
from bot_detector.event_queue.adapters.kafka import AIOKafkaConsumerAdapter
from bot_detector.firehose.app.auth.auth import ANONYMOUS, AuthUser
from bot_detector.firehose.app.consumer import QueueRepo
from bot_detector.firehose.core.config import Settings

TOPIC = "players.scraped"


@pytest.fixture(autouse=True)
def kafka_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOTSTRAP_SERVERS", "localhost:9092")


@pytest.fixture
def repo() -> QueueRepo:
    return QueueRepo(settings=Settings())


def test_resolve_consumer_group_anonymous(repo: QueueRepo):
    assert (
        repo.resolve_consumer_group(user=ANONYMOUS, topic=TOPIC)
        == "fh-anonymous-players.scraped"
    )


def test_resolve_consumer_group_keyed_is_stable_and_unique(repo: QueueRepo):
    user_one = AuthUser(name="system-one")
    user_two = AuthUser(name="system-two")
    group_one = repo.resolve_consumer_group(user=user_one, topic=TOPIC)
    group_two = repo.resolve_consumer_group(user=user_two, topic=TOPIC)

    assert group_one.startswith("fh-players.scraped-system-one")
    assert group_two.startswith("fh-players.scraped-system-two")
    assert group_one == repo.resolve_consumer_group(user=user_one, topic=TOPIC)
    assert group_one != group_two


def test_resolve_consumer_group_strips_discord_prefix(repo: QueueRepo):
    user = AuthUser(name="discord_123456789012345678")
    group = repo.resolve_consumer_group(user=user, topic=TOPIC)
    assert group == "fh-players.scraped-123456789012345678"


def test_resolve_consumer_group_is_topic_scoped(repo: QueueRepo):
    user = AuthUser(name="system-one")
    assert repo.resolve_consumer_group(
        user=user, topic=TOPIC
    ) != repo.resolve_consumer_group(user=user, topic="reports.to_insert")


def test_create_consumer_reports_uses_reports_struct(repo: QueueRepo):
    consumer = repo.create_consumer(user=ANONYMOUS, topic="reports.to_insert")

    assert not isinstance(consumer, Exception)
    backend = consumer._backend
    assert isinstance(backend, AIOKafkaConsumerAdapter)
    assert backend.config.topic == "reports.to_insert"


def test_create_consumer_anonymous_uses_shared_group_earliest(repo: QueueRepo):
    consumer = repo.create_consumer(user=ANONYMOUS, topic=TOPIC)

    assert not isinstance(consumer, Exception)
    backend = consumer._backend
    assert isinstance(backend, AIOKafkaConsumerAdapter)
    assert backend.config.consumer_config is not None
    assert backend.config.consumer_config.group_id == "fh-anonymous-players.scraped"
    assert backend.config.consumer_config.auto_offset_reset == "earliest"
    assert backend.config.topic == "players.scraped"


def test_create_consumer_keyed_uses_own_group_earliest(repo: QueueRepo):
    user = AuthUser(name="system-one")
    consumer = repo.create_consumer(user=user, topic=TOPIC)

    assert not isinstance(consumer, Exception)
    backend = consumer._backend
    assert isinstance(backend, AIOKafkaConsumerAdapter)
    assert backend.config.consumer_config is not None
    group_id = backend.config.consumer_config.group_id
    assert group_id == repo.resolve_consumer_group(user=user, topic=TOPIC)
    assert backend.config.consumer_config.auto_offset_reset == "earliest"
