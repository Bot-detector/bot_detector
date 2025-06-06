import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "true"

from bot_detector.hiscore_scraper import core


def test_sample():
    assert core is not None
