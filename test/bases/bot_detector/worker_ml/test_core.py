import os

os.environ.setdefault("BASE_URL", "http://localhost")
os.environ.setdefault("MODEL_NAME", "dummy")

from bot_detector.worker_ml import core


def test_sample():
    assert core is not None
