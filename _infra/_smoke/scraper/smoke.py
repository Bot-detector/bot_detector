"""Fetch-level container smoke test: the real brick against the live API.

Runs inside the hiscore_scraper image on the compose network; needs
outbound internet only - no kafka, mysql or proxies. Covers what the
simulated unit tests cannot: real redirect following, real timeout
timers, and the live payload shape against the PlayerStats validators.

Run from the repo root: make smoke-scraper
Prints PASS/FAIL lines; exit 1 on any failure.
"""

import asyncio
import sys
import time

from aiohttp import ClientTimeout
from bot_detector.hiscore_scraper.scraping.session import build_session
from bot_detector.osrs_hs_api.core import HiscoreOldSchoolAPI
from bot_detector.osrs_hs_api.exceptions import Err, Ok, PlayerDoesNotExist
from bot_detector.osrs_hs_api.structs import EXPECTED_SKILL_IDS

BLACKHOLE = (
    "http://10.255.255.1:81"  # unroutable: connect hangs until the timeout fires
)
TIMEOUT_BUDGET_S = 15.0  # wall-clock slack over the 10s total (connect 5 fires first)

PASS = 0
FAIL = 0


def _assert(condition: bool, label: str, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label} — {detail}")


async def main() -> None:
    api = HiscoreOldSchoolAPI()
    _assert(
        api.timeout == ClientTimeout(total=10, connect=5),
        "default timeout is 10s total / 5s connect",
        f"got {api.timeout}",
    )

    async with build_session() as session:
        print("[GET real player: Zezima]")
        started = time.monotonic()
        result = await api.get("Zezima", session)
        elapsed = time.monotonic() - started
        _assert(isinstance(result, Ok), "fetch returns Ok", f"got {result!r:.200}")
        if isinstance(result, Ok):
            ids = {s.id for s in result.value.skills}
            _assert(
                EXPECTED_SKILL_IDS.issubset(ids),
                "live payload passes the full-skill-set validator",
                f"got {len(ids)} skill ids",
            )
            _assert(elapsed < 10.0, "success within the 10s bound", f"{elapsed:.2f}s")

        print("[GET missing player]")
        result = await api.get("zzqqxwvu0000", session)
        got = (
            type(result.error).__name__
            if isinstance(result, Err)
            else f"{result!r:.200}"
        )
        _assert(
            isinstance(result, Err) and isinstance(result.error, PlayerDoesNotExist),
            "missing player is Err(PlayerDoesNotExist)",
            got,
        )

        print("[GET through blackhole address]")
        started = time.monotonic()
        result = await api.get("player", session, proxy=BLACKHOLE)
        elapsed = time.monotonic() - started
        _assert(
            isinstance(result, Err), "blackhole fetch returns Err", f"{result!r:.200}"
        )
        _assert(
            elapsed < TIMEOUT_BUDGET_S,
            "timeout bound holds under real timers",
            f"{elapsed:.2f}s",
        )

    print(f"\n{'=' * 50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
