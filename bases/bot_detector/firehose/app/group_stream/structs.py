import orjson
from pydantic import BaseModel

QUEUE_MAX_SIZE = 1000


def serialize(message: BaseModel) -> str:
    return orjson.dumps(message.model_dump()).decode("utf-8")
