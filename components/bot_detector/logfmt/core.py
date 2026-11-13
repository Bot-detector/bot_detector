import atexit
import logging
import logging.handlers
from datetime import datetime, timezone
from queue import Queue

import orjson
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_FILE_BYTES = 50_000_000
MAX_FILE_BACKUPS = 5


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOGFMT_")

    DEBUG: bool = False
    TO_FILE: str | None = None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "lvl": record.levelname,
            "name": record.name,
            "func": record.funcName,
            "line": record.lineno,
        }
        if isinstance(record.msg, dict):
            # msg. prefix keeps logged keys from clobbering ts/lvl/name/line
            log_record.update({f"msg.{k}": v for k, v in record.msg.items()})
        else:
            log_record["msg"] = record.getMessage()

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return orjson.dumps(log_record, default=str).decode()


def _build_handlers(settings: Settings) -> list[logging.Handler]:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if settings.TO_FILE:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=settings.TO_FILE,
            maxBytes=MAX_FILE_BYTES,
            backupCount=MAX_FILE_BACKUPS,
            # defer open so an unwritable path cannot crash at import time
            delay=True,
        )
        handlers.append(file_handler)
    for handler in handlers:
        handler.setFormatter(JsonFormatter())
    return handlers


_configured = False


def setup_logging(settings: Settings | None = None) -> None:
    """Configure root logging once.

    Skips loudly when root already has handlers, since basicConfig would
    silently no-op and drop the JSON format without anyone noticing.
    """
    global _configured
    if _configured:
        return
    _configured = True

    config = settings or Settings()
    root = logging.getLogger()
    if root.handlers:
        logging.getLogger("bot_detector.logfmt").warning(
            "root logger already configured; logfmt setup skipped"
        )
        return

    # queue handler keeps blocking stderr/file writes off the event loop
    q_handler = logging.handlers.QueueHandler(Queue())
    logging.basicConfig(
        level=logging.DEBUG if config.DEBUG else logging.INFO,
        handlers=[q_handler],
    )
    listener = logging.handlers.QueueListener(q_handler.queue, *_build_handlers(config))
    listener.start()
    # daemon thread dies abruptly at exit; stop() flushes the queue first
    atexit.register(listener.stop)

    logging.getLogger("asyncmy").setLevel(logging.ERROR)


setup_logging()
