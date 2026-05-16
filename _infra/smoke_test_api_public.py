"""
Smoke test script for api_public.
Run against a running service: python _infra/smoke_test_api_public.py
"""

import argparse
import asyncio
import sys

import aiohttp


BASE = "/v2"
PASS = 0
FAIL = 0


def _assert(condition: bool, label: str, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label} — {detail}")


async def smoke(session: aiohttp.ClientSession, url: str):
    print(f"\nSmoke testing {url}\n")

    await _root(session, url)
    await _labels(session, url)
    await _player_report_score(session, url)
    await _player_feedback_score(session, url)
    await _player_prediction(session, url)
    await _feedback_export(session, url)
    await _feedback_export_no_auth(session, url)
    await _post_feedback(session, url)
    await _post_report(session, url)
    await _users_me(session, url)
    await _users_me_no_auth(session, url)

    print(f"\n{'=' * 50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


async def _root(session: aiohttp.ClientSession, url: str):
    print("[GET /]")
    async with session.get(f"{url}/") as resp:
        body = await resp.json()
        _assert(resp.status == 200, "status 200", f"got {resp.status}")
        _assert("message" in body, "has message field", f"got {body}")


async def _labels(session: aiohttp.ClientSession, url: str):
    print("[GET /v2/labels]")
    async with session.get(f"{url}{BASE}/labels") as resp:
        body = await resp.json()
        _assert(resp.status == 200, "status 200", f"got {resp.status}")
        _assert(isinstance(body, list) and len(body) > 0, "returns non-empty list")
        _assert(
            "id" in body[0] and "label" in body[0],
            "items have id + label fields",
        )

    print("[GET /v2/labels/1]")
    async with session.get(f"{url}{BASE}/labels/1") as resp:
        body = await resp.json()
        _assert(resp.status == 200, "status 200", f"got {resp.status}")
        _assert(body["id"] == 1, "label id == 1")


async def _player_report_score(session: aiohttp.ClientSession, url: str):
    print("[GET /v2/player/report/score?name=extreme4all]")
    async with session.get(
        f"{url}{BASE}/player/report/score", params={"name": "extreme4all"}
    ) as resp:
        body = await resp.json()
        _assert(resp.status == 200, "status 200", f"got {resp.status}")
        _assert(isinstance(body, list), "returns list")


async def _player_feedback_score(session: aiohttp.ClientSession, url: str):
    print("[GET /v2/player/feedback/score?name=extreme4all]")
    async with session.get(
        f"{url}{BASE}/player/feedback/score", params={"name": "extreme4all"}
    ) as resp:
        body = await resp.json()
        _assert(resp.status == 200, "status 200", f"got {resp.status}")
        _assert(isinstance(body, list), "returns list")


async def _player_prediction(session: aiohttp.ClientSession, url: str):
    print("[GET /v2/player/prediction?name=extreme4all&breakdown=true]")
    async with session.get(
        f"{url}{BASE}/player/prediction",
        params={"name": "extreme4all", "breakdown": "true"},
    ) as resp:
        body = await resp.json()
        _assert(resp.status in (200, 404), "status 200 or 404", f"got {resp.status}")
        if resp.status == 200:
            _assert(isinstance(body, list) and len(body) > 0, "returns non-empty list")
            _assert(
                "player_name" in body[0] and "prediction_label" in body[0],
                "has prediction fields",
            )


async def _feedback_export(session: aiohttp.ClientSession, url: str):
    print("[GET /v2/feedback/export?player_name=extreme4all — with auth]")
    async with session.get(
        f"{url}{BASE}/feedback/export",
        params={"player_name": "extreme4all"},
        auth=aiohttp.BasicAuth("testuser", "test-token-123"),
    ) as resp:
        _assert(resp.status in (200, 204), "status 200 or 204", f"got {resp.status}")
        if resp.status == 200:
            body = await resp.json()
            _assert("player_name" in body, "has player_name")
            _assert("feedback" in body, "has feedback list")
            _assert(isinstance(body["feedback"], list), "feedback is list")


async def _feedback_export_no_auth(session: aiohttp.ClientSession, url: str):
    print("[GET /v2/feedback/export — no auth]")
    async with session.get(
        f"{url}{BASE}/feedback/export",
        params={"player_name": "extreme4all"},
    ) as resp:
        _assert(
            resp.status == 401,
            "status 401 without auth",
            f"got {resp.status}",
        )


async def _post_feedback(session: aiohttp.ClientSession, url: str):
    print("[POST /v2/feedback]")
    payload = {
        "player_name": "extreme4all",
        "vote": 1,
        "prediction": "Real_Player",
        "confidence": 0.9,
        "subject_id": 2,
        "feedback_text": "smoke test",
        "proposed_label": "Real_Player",
    }
    async with session.post(f"{url}{BASE}/feedback", json=payload) as resp:
        body = await resp.json()
        _assert(
            resp.status in (201, 422),
            "status 201 or 422 (dupe)",
            f"got {resp.status} detail={body.get('detail', '')}",
        )


async def _post_report(session: aiohttp.ClientSession, url: str):
    print("[POST /v2/report]")
    payload = [
        {
            "reporter": "extreme4all",
            "reported": "ferrariic",
            "region_id": 12345,
            "x_coord": 100,
            "y_coord": 200,
            "z_coord": 0,
            "ts": 9999999999,
            "manual_detect": 0,
            "on_members_world": 1,
            "on_pvp_world": 0,
            "world_number": 400,
            "equipment": {},
            "equip_ge_value": 0,
        }
    ]
    async with session.post(f"{url}{BASE}/report", json=payload) as resp:
        body = await resp.json()
        _assert(
            resp.status in (201, 500),
            "status 201 or 500 (queue unavailable)",
            f"got {resp.status} detail={body.get('detail', '')}",
        )


async def _users_me(session: aiohttp.ClientSession, url: str):
    print("[GET /v2/users/me — with auth]")
    async with session.get(
        f"{url}{BASE}/users/me",
        auth=aiohttp.BasicAuth("testuser", "test-token-123"),
    ) as resp:
        body = await resp.json()
        _assert(resp.status == 200, "status 200", f"got {resp.status}")
        _assert(body.get("username") == "testuser", "username == testuser")


async def _users_me_no_auth(session: aiohttp.ClientSession, url: str):
    print("[GET /v2/users/me — no auth]")
    async with session.get(f"{url}{BASE}/users/me") as resp:
        _assert(
            resp.status == 401,
            "status 401 without auth",
            f"got {resp.status}",
        )


def main():
    parser = argparse.ArgumentParser(description="Smoke test api_public")
    parser.add_argument(
        "--url", default="http://localhost:5000", help="Base URL of the service"
    )
    args = parser.parse_args()

    asyncio.run(smoke(aiohttp.ClientSession(), args.url))


if __name__ == "__main__":
    main()
