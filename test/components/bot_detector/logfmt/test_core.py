import logging
import logging.handlers
import sys
from datetime import datetime

import orjson
from bot_detector.logfmt import core


def _record(
    msg: object,
    args: tuple | None = None,
    exc_info=None,
    level: int = logging.INFO,
) -> logging.LogRecord:
    return logging.LogRecord(
        name="bot_detector.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=exc_info,
        func="_record",
    )


def test_format_outputs_valid_json():
    record = _record("hello %s", args=("world",))
    parsed = orjson.loads(core.JsonFormatter().format(record))
    assert parsed["msg"] == "hello world"
    assert parsed["lvl"] == "INFO"
    assert parsed["name"] == "bot_detector.test"
    assert parsed["func"] == "_record"
    assert parsed["line"] == 1


def test_format_dict_msg_is_prefixed():
    record = _record({"user_id": 7, "ts": "fake"})
    parsed = orjson.loads(core.JsonFormatter().format(record))
    assert parsed["msg.user_id"] == 7
    assert parsed["ts"] != "fake"


def test_format_falls_back_to_raw_text_on_bad_payload():
    record = _record({"headers": {4: "x"}})  # nested non-str key breaks orjson
    formatted = core.JsonFormatter().format(record)
    assert formatted.startswith("logfmt_json_fallback: ")
    assert "headers" in formatted


def test_format_fallback_keeps_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record({"headers": {4: "x"}}, exc_info=sys.exc_info())
    formatted = core.JsonFormatter().format(record)
    assert formatted.startswith("logfmt_json_fallback: ")
    assert "ValueError" in formatted


def test_format_includes_exception_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record("failed", exc_info=sys.exc_info())
    parsed = orjson.loads(core.JsonFormatter().format(record))
    assert "ValueError" in parsed["exception"]
    assert "boom" in parsed["exception"]


def test_ts_is_iso8601_with_timezone():
    record = _record("hello")
    parsed = orjson.loads(core.JsonFormatter().format(record))
    ts = datetime.fromisoformat(parsed["ts"])
    assert ts.tzinfo is not None


def test_settings_reads_prefixed_env(monkeypatch):
    monkeypatch.setenv("LOGFMT_DEBUG", "true")
    settings = core.Settings()
    assert settings.DEBUG is True


def test_settings_ignores_unprefixed_env(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    settings = core.Settings()
    assert settings.DEBUG is False


def test_build_handlers_adds_rotating_file(tmp_path):
    settings = core.Settings(TO_FILE=str(tmp_path / "app.json"))
    handlers = core._build_handlers(settings)
    try:
        assert len(handlers) == 2
        assert isinstance(handlers[1], logging.handlers.RotatingFileHandler)
    finally:
        for handler in handlers:
            handler.close()


def test_build_handlers_stream_only_without_to_file():
    handlers = core._build_handlers(core.Settings())
    try:
        assert len(handlers) == 1
        assert all(isinstance(h.formatter, core.JsonFormatter) for h in handlers)
    finally:
        for handler in handlers:
            handler.close()


def test_setup_logging_is_idempotent():
    before = len(logging.getLogger().handlers)
    core.setup_logging()
    core.setup_logging()
    assert len(logging.getLogger().handlers) == before
