import logging

import pytest


@pytest.fixture(autouse=True)
def configure_logger(caplog):
    """
    Configure the logger globally for all tests and clear logs between tests.
    """
    caplog.set_level(logging.INFO, logger="bot_detector.scrape_task_producer.core")
    yield caplog
    # Clear captured logs after each test
    caplog.clear()
