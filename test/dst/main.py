"""Generic DST launcher: run any scenario on the virtual clock.

    # zero-wiring target (pure asyncio scenario)
    uv run python -m dst.main dst.scenarios.kafka_smoke

    # app scenario with knobs: module[:function], runner deadline,
    # clock start, typed kwargs forwarded to the scenario's main()
    uv run python -m dst.main dst.scenarios.firehose \
        --until 120 --seed-independent-clock 0 \
        --kw duration_s=60 --kw feed_rate_s=1000 --kw n_clients=10

The target function must be a coroutine function; it receives only the
--kw arguments (typed: int, float, bool, else str). The launcher knows
nothing about the app - seam patching lives in the scenario module.

Output: one JSON object with the SimResult fields plus the scenario's
return value; exit 0 on a completed scenario, 1 on error/timeout.
"""

import argparse
import ast
import dataclasses
import importlib
import inspect
from collections.abc import Sequence
from typing import Any

import orjson
from pydantic import BaseModel

from dst import SimResult, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dst", description="run a scenario on the DST virtual clock"
    )
    parser.add_argument(
        "target",
        help="module[:function] to run; function defaults to 'main'",
    )
    parser.add_argument(
        "--until",
        type=float,
        default=None,
        help="virtual-time deadline in seconds (stops a scenario that "
        "never finishes on its own)",
    )
    parser.add_argument("--start", type=float, default=0.0, help="clock start")
    parser.add_argument(
        "--kw",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="scenario kwarg; value parsed as bool/int/float/str",
    )
    parser.add_argument(
        "--json-pretty", action="store_true", help="pretty-print the result JSON"
    )
    return parser


def _parse_value(raw: str) -> Any:
    lowered = raw.strip().lower()
    if lowered in ("true", "false", "null", "none"):
        return {"true": True, "false": False, "null": None, "none": None}[lowered]
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return raw


def resolve_target(target: str) -> tuple[Any, str]:
    module_name, _, function_name = target.partition(":")
    module = importlib.import_module(module_name)
    function = getattr(module, function_name or "main")
    if not inspect.iscoroutinefunction(function):
        raise TypeError(f"{target} is not a coroutine function")
    return function, target


def result_to_dict(result: SimResult) -> dict[str, Any]:
    value: Any = result.value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    elif value is not None and not isinstance(value, (str, int, float, bool, list)):
        value = repr(value)
    return {
        "virtual_time_s": result.virtual_time_s,
        "wall_time_s": result.wall_time_s,
        "done": result.done,
        "value": value,
        "error": str(result.error) if result.error else None,
        "pending_tasks": result.pending_tasks,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kwargs = dict(kv.split("=", 1) for kv in args.kw)
    kwargs = {key: _parse_value(raw) for key, raw in kwargs.items()}
    try:
        function, target = resolve_target(args.target)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        print(orjson.dumps({"error": str(exc)}).decode())
        return 1
    result = run(
        function(**kwargs),
        start_s=args.start,
        until_s=args.until,
    )
    payload = result_to_dict(result)
    payload["target"] = target
    indent = 2 if args.json_pretty else None
    print(orjson.dumps(payload, option=orjson.OPT_INDENT_2 if indent else 0).decode())
    return 0 if result.done and result.error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
