import os

from bot_detector.hiscore_scraper import core

os.environ["ENVIRONMENT"] = "test"


def test_sample():
    assert core is not None
