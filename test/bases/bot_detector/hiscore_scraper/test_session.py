"""Cookie contract for the scraper session.

Jagex's edge serves the hiscores "down" page (302 -> /community) when it
receives quoted-empty tracking cookies (JGSTAFFNAME=""/JGSTAFFPASS=""), so
build_session() must never send cookies at all.
"""

import re

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from bot_detector.hiscore_scraper import core

# any quoted-empty cookie is poison (aiohttp >= 3.12.7 quoting); Jagex
# currently only issues empties for JGSTAFFNAME/JGSTAFFPASS, this catches
# future additions too
QUOTED_TRACKING = re.compile(r'\w+=""')


def assert_no_tracking_cookies(cookie_header: str | None) -> None:
    assert cookie_header is None or not QUOTED_TRACKING.search(cookie_header), (
        f"quoted-empty tracking cookies sent to Jagex: {cookie_header!r}"
    )


@pytest.mark.asyncio
async def test_build_session_sends_no_cookies():
    seen: dict = {}

    async def set_cookie(request: web.Request) -> web.Response:
        seen["set_cookie_called"] = True
        resp = web.Response(text="ok")
        # host-only, no Secure attribute: would be echoed by a default jar
        resp.set_cookie("JGTEST", "abc123")
        return resp

    async def check(request: web.Request) -> web.Response:
        seen["cookie_header"] = request.headers.get("Cookie")
        assert_no_tracking_cookies(seen["cookie_header"])
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/set", set_cookie)
    app.router.add_get("/check", check)
    server = TestServer(app)
    await server.start_server()
    try:
        session = core.build_session()
        async with session:
            await session.get(str(server.make_url("/set")))
            await session.get(str(server.make_url("/check")))
    finally:
        await server.close()

    assert seen["set_cookie_called"] is True
    # strongest contract: nothing at all, not even unquoted cookies
    assert seen["cookie_header"] is None


@pytest.mark.parametrize(
    "cookie_header,should_fail",
    [
        (None, False),
        ("JGSTAFFNAME=; JGSTAFFPASS=", False),
        ("__cf_bm=abc; JXTRACKING=01B2", False),
        ('JGSTAFFNAME=""; JGSTAFFPASS=""', True),
        ('__cf_bm=abc; JGSTAFFNAME=""', True),
        ('settings="wwGlr"; JXWEBUID=""', True),
    ],
)
def test_quoted_tracking_cookies_are_detected(cookie_header, should_fail: bool):
    if should_fail:
        with pytest.raises(AssertionError, match="quoted-empty tracking cookies"):
            assert_no_tracking_cookies(cookie_header)
    else:
        assert_no_tracking_cookies(cookie_header)


@pytest.mark.asyncio
async def test_build_session_keeps_user_agent():
    seen: dict = {}

    async def check(request: web.Request) -> web.Response:
        seen["ua"] = request.headers.get("User-Agent")
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/check", check)
    server = TestServer(app)
    await server.start_server()
    try:
        session = core.build_session()
        async with session:
            await session.get(str(server.make_url("/check")))
    finally:
        await server.close()

    assert seen["ua"] == "http://osrsbotdetector.com"
