import asyncio
from dataclasses import dataclass

import orjson
from pydantic import BaseModel

QUEUE_MAX_SIZE = 1000


@dataclass
class Inbox:
    """Per-connection fan-out queue; the name identifies the connection."""

    name: str
    queue: asyncio.Queue


def serialize(message: BaseModel) -> str:
    return orjson.dumps(message.model_dump()).decode("utf-8")
