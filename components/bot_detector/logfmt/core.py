import ast
import json
import logging

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG: bool = False


def can_convert_to_json(s: str) -> dict | None:
    try:
        result = ast.literal_eval(s)
        return result if isinstance(result, dict) else None
    except ValueError:
        return None


# Configure JSON logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "ts": self.formatTime(record, self.datefmt),
            "lvl": record.levelname,
            "name": record.name,
            "func": record.funcName,
            "line": record.lineno,
        }

        msg = record.getMessage()
        if msg_dict := can_convert_to_json(msg):
            log_record.update({f"msg.{k}": v for k, v in msg_dict.items()})
        else:
            log_record["msg"] = msg

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


class IgnoreSQLWarnings(logging.Filter):
    def filter(self, record):
        ignore_messages = ["Unknown table", "Duplicate entry"]
        # Check if any of the ignore messages are in the log record message
        if any(msg in record.getMessage() for msg in ignore_messages):
            return False  # Don't log
        return True  # Log


# Set up the logger
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())


logging.basicConfig(level=logging.INFO, handlers=[handler])

level = logging.DEBUG if Settings().DEBUG else logging.INFO
logging.getLogger("bot_detector").setLevel(level=level)

# set imported loggers to warning
logging.getLogger("asyncmy").addFilter(IgnoreSQLWarnings())
