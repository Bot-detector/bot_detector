"""dst launcher: target resolution, kwarg typing, CLI end-to-end."""

import pytest

from dst.main import _parse_value, main, resolve_target


def test_resolve_target_default_function():
    function, target = resolve_target("dst.scenarios.kafka_smoke")
    assert target == "dst.scenarios.kafka_smoke"
    import inspect

    assert inspect.iscoroutinefunction(function)


def test_resolve_target_explicit_function():
    function, target = resolve_target("dst.scenarios.firehose:main")
    assert target == "dst.scenarios.firehose:main"
    import inspect

    assert inspect.iscoroutinefunction(function)


def test_resolve_target_rejects_non_coroutine():
    with pytest.raises(TypeError, match="not a coroutine function"):
        resolve_target("dst.main:build_parser")


def test_resolve_target_unknown_module():
    with pytest.raises(ModuleNotFoundError):
        resolve_target("dst.nope:main")


def test_parse_value_types():
    assert _parse_value("42") == 42
    assert _parse_value("0.5") == 0.5
    assert _parse_value("true") is True
    assert _parse_value("False") is False
    assert _parse_value("null") is None
    assert _parse_value("[1, 2]") == [1, 2]
    assert _parse_value("hello") == "hello"
    assert _parse_value("players.scraped") == "players.scraped"


def test_cli_runs_scenario_and_prints_json(capsys):
    code = main(
        [
            "dst.scenarios.kafka_smoke",
            "--kw",
            "duration_s=5",
            "--kw",
            "feed_rate_s=100",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    payload = __import__("json").loads(out)
    assert payload["done"] is True
    assert payload["error"] is None
    assert payload["value"]["consumed"] == pytest.approx(500, rel=0.01)
    assert payload["virtual_time_s"] == pytest.approx(5.0, abs=0.05)


def test_cli_failure_exits_nonzero(capsys):
    code = main(
        [
            "dst.scenarios.kafka_smoke",
            "--kw",
            "duration_s=2",
            "--kw",
            "feed_rate_s=100",
            "--until",
            "1",
        ]
    )
    payload = __import__("json").loads(capsys.readouterr().out)
    assert code == 1
    assert payload["done"] is False


def test_cli_unknown_target_exits_nonzero(capsys):
    code = main(["dst.nope"])
    assert code == 1
    assert "error" in capsys.readouterr().out
