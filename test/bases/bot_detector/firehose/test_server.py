import os

# server.py builds the app (and the lazy db engine) at import time, so
# the env must exist before the import; nothing is contacted
os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

import pytest  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402


def test_create_app_rejects_unknown_topic_names():
    with pytest.raises(ValueError, match="unknown topics"):
        create_app(
            Settings(
                public_topics={"players.scraped", "bogus.topic"},
                keyed_topics={"reports.to_insert"},
            )
        )
