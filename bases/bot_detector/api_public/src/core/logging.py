import json
import logging


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
            log_record.update(record.msg)
        else:
            log_record["msg"] = record.getMessage()

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record, default=str)


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
logging.getLogger("asyncmy").addFilter(IgnoreSQLWarnings())
