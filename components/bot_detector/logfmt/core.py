import logging

import orjson
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG: bool = False
    TO_FILE: str | None = None


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
        if isinstance(record.msg, dict):
            log_record.update({f"msg.{k}": v for k, v in record.msg.items()})
        else:
            log_record["msg"] = record.getMessage()

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return orjson.dumps(log_record, default=str).decode()


class IgnoreSQLWarnings(logging.Filter):
    def filter(self, record):
        ignore_messages = ["Unknown table", "Duplicate entry"]
        # Check if any of the ignore messages are in the log record message
        if any(msg in record.getMessage() for msg in ignore_messages):
            return False  # Don't log
        return True  # Log


# Set up the logger
settings = Settings()

handlers: list[logging.Handler] = [logging.StreamHandler()]
for h in handlers:
    h.setFormatter(JsonFormatter())

if settings.TO_FILE:
    file_handler = logging.FileHandler(settings.TO_FILE)  # append mode
    file_handler.setFormatter(JsonFormatter())
    handlers.append(file_handler)

logging.basicConfig(level=logging.INFO, handlers=handlers)

level = logging.DEBUG if settings.DEBUG else logging.INFO
logging.getLogger("bot_detector").setLevel(level=level)

# set imported loggers to warning
logging.getLogger("asyncmy").addFilter(IgnoreSQLWarnings())
