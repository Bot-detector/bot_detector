"""Unit tests for dump_error: JSON-safe error serialization."""

from aiohttp import ClientResponseError, RequestInfo
from bot_detector.hiscore_scraper.errors import dump_error
from multidict import CIMultiDict
from yarl import URL

URL_HS = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.json"


def _gateway_error() -> ClientResponseError:
    return ClientResponseError(
        request_info=RequestInfo(
            url=URL(f"{URL_HS}?player=x"),
            method="GET",
            headers=CIMultiDict(),
        ),
        history=(),
        status=502,
        message="Bad Gateway",
        headers=CIMultiDict(
            {
                "Date": "Thu, 12 Nov 2026 13:26:20 GMT",
                "Content-Type": "text/html",
                "Server": "cloudflare",
                "Set-Cookie": "__cf_bm=cookie-value; HttpOnly; SameSite=None",
                "Strict-Transport-Security": "max-age=31536000;",
                "cf-cache-status": "DYNAMIC",
                "CF-RAY": "a595de2848fc8e6a-SJC",
            }
        ),
    )


def test_known_class_gets_structured_fields():
    dumped = dump_error(_gateway_error())

    assert dumped["type"] == "ClientResponseError"
    assert dumped["status"] == 502
    assert dumped["message"] == "Bad Gateway"
    assert dumped["url"] == f"{URL_HS}?player=x"
    assert dumped["method"] == "GET"
    assert dumped["headers"] == {
        "Date": "Thu, 12 Nov 2026 13:26:20 GMT",
        "Content-Type": "text/html",
        "Server": "cloudflare",
        "Strict-Transport-Security": "max-age=31536000;",
        "cf-cache-status": "DYNAMIC",
        "CF-RAY": "a595de2848fc8e6a-SJC",
    }


def test_set_cookie_never_leaks():
    dumped = dump_error(_gateway_error())

    assert dumped["headers"] is not None
    assert all(key.lower() != "set-cookie" for key in dumped["headers"])
    assert "cookie-value" not in str(dumped)


def test_unknown_class_falls_back_to_text():
    error = RuntimeError("proxy pool exhausted")
    assert dump_error(error) == {
        "type": "RuntimeError",
        "message": "proxy pool exhausted",
    }


def test_empty_message_falls_back_to_repr():
    error = TimeoutError()
    dumped = dump_error(error)

    assert dumped["type"] == "TimeoutError"
    assert dumped["repr"] == repr(error)
