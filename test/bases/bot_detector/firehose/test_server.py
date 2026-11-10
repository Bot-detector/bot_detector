import os

# server.py builds the app (and the lazy db engine) at import time, so
# the env must exist before the import; nothing is contacted
os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

import pytest  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402


def test_create_app_rejects_access_maps_that_do_not_cover_the_catalog():
    # a missing entry would silently publish a topic to anonymous
    # callers; an unknown entry is silently inert - both refuse to boot
    with pytest.raises(ValueError, match="missing topics"):
        create_app(Settings(topic_access={"reports.to_insert": "keyed"}))
    with pytest.raises(ValueError, match="unknown topics"):
        create_app(
            Settings(topic_access={**Settings().topic_access, "bogus.topic": "keyed"})
        )
