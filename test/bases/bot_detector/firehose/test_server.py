import os

# server.py builds the app (and the lazy db engine) at import time, so
# the env must exist before the import; nothing is contacted
os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

import pytest  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402

# a full, valid pair of lists: each rejection case below perturbs it
FULL_PUBLIC = {"players.scraped", "players.not_found", "predictions.to_insert"}
FULL_KEYED = {"reports.to_insert"}


def test_create_app_rejects_topic_lists_that_do_not_cover_the_catalog():
    with pytest.raises(ValueError, match="missing topics"):
        create_app(Settings(public_topics={"players.scraped"}, keyed_topics=set()))
    with pytest.raises(ValueError, match="unknown topics"):
        create_app(
            Settings(
                public_topics={*FULL_PUBLIC, "bogus.topic"},
                keyed_topics=FULL_KEYED,
            )
        )


def test_create_app_rejects_topics_in_both_lists():
    with pytest.raises(ValueError, match="overlap"):
        create_app(
            Settings(
                public_topics={*FULL_PUBLIC, "reports.to_insert"},
                keyed_topics=FULL_KEYED,
            )
        )
