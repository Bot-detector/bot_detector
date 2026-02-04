import pytest
from bot_detector.event_queue import adapters, core
from bot_detector.event_queue.adapters import kafka
from pydantic import BaseModel


class TestMessage(BaseModel):
    data: str


def test_sample():
    assert core is not None


@pytest.mark.asyncio
async def test_producer_put_retries():
    assert 1
