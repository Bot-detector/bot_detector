import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from bot_detector.discord_webhook import DiscordWebhookRepo, Embed


def _resp(
    status: int,
    json_data: dict | None = None,
    text: str = "",
    headers: dict | None = None,
):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data if json_data is not None else {})
    resp.text = AsyncMock(return_value=text)
    resp.headers = headers or {}
    # usable as `async with session.post(...) as resp:`
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session(responses: list):
    # session.post() is used as an async context manager by the transport,
    # so a plain MagicMock returning the scripted responses is the contract.
    return MagicMock(post=MagicMock(side_effect=responses))


@pytest.mark.asyncio
async def test_post_success_returns_none_on_200_and_204(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
    for status in (200, 204):
        repo = DiscordWebhookRepo(session=_session([_resp(status)]))
        err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
        assert err is None


@pytest.mark.asyncio
async def test_post_returns_error_value_on_http_failure(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
    repo = DiscordWebhookRepo(session=_session([_resp(400, text="bad embed")]))
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert isinstance(err, Exception)
    assert "400" in str(err)
    assert "bad embed" in str(err)


@pytest.mark.asyncio
async def test_post_retries_on_429_then_succeeds(monkeypatch):
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)
        return None

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    repo = DiscordWebhookRepo(
        session=_session([_resp(429, json_data={"retry_after": 1.5}), _resp(204)])
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert sleeps == [1.5]


@pytest.mark.asyncio
async def test_post_gives_up_after_max_429s_without_extra_sleep(monkeypatch):
    """Bug (legacy parity): the retry loop slept retry_after even on the
    final attempt, then failed anyway - pure wasted wall clock."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)
        return None

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    repo = DiscordWebhookRepo(
        session=_session(
            [_resp(429, json_data={"retry_after": 60.0}) for _ in range(3)]
        )
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert isinstance(err, Exception)
    assert "rate limited" in str(err)
    assert sleeps == [60.0, 60.0]  # no sleep after the last attempt


@pytest.mark.asyncio
async def test_post_falls_back_for_malformed_429(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
    repo = DiscordWebhookRepo(
        session=_session([_resp(429, json_data=None), _resp(204)])
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert repo.session.post.call_count == 2


@pytest.mark.asyncio
async def test_post_uses_retry_after_header_when_body_missing_it(monkeypatch):
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)
        return None

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    repo = DiscordWebhookRepo(
        session=_session(
            [_resp(429, json_data={}, headers={"Retry-After": "0.25"}), _resp(204)]
        )
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_post_client_error_returned_as_value():
    """Contract: transport failures (DNS, connect, reset) must come back as
    an Exception value so a broadcast loop can log and continue - the legacy
    code swallowed them silently, an earlier draft let them crash the job."""
    session = MagicMock(
        post=MagicMock(side_effect=aiohttp.ClientError("connection reset"))
    )
    repo = DiscordWebhookRepo(session=session)
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert isinstance(err, Exception)
    assert "connection reset" in str(err)


@pytest.mark.asyncio
async def test_post_timeout_returned_as_value():
    """TimeoutError is not an aiohttp.ClientError subclass; it must be
    caught too or a hung endpoint aborts the whole broadcast."""
    session = MagicMock(post=MagicMock(side_effect=TimeoutError()))
    repo = DiscordWebhookRepo(session=session)
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert isinstance(err, Exception)


@pytest.mark.asyncio
async def test_post_payload_contains_embeds_and_content():
    resp = _resp(204)
    session = MagicMock(post=MagicMock(return_value=resp))
    repo = DiscordWebhookRepo(session=session)

    err = await repo.post(
        url="http://hook",
        embeds=[Embed(title="t", description="d")],
        content="ping",
    )

    assert err is None
    kwargs = session.post.call_args.kwargs
    assert kwargs["json"] == {
        "embeds": [
            {"title": "t", "color": 0, "fields": [], "description": "d"},
        ],
        "content": "ping",
    }


@pytest.mark.asyncio
async def test_post_survives_non_object_429_body(monkeypatch):
    """A non-object JSON 429 body (list / string / null, e.g. from a proxy)
    must fall back to the default retry_after, never raise - post()'s
    contract is errors as values, and data.get on a list raised
    AttributeError out of post() before the except was widened."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
    repo = DiscordWebhookRepo(
        session=_session([_resp(429, json_data=[1, 2]), _resp(204)])
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert repo.session.post.call_count == 2


@pytest.mark.asyncio
async def test_post_survives_null_retry_after_in_429_body(monkeypatch):
    """{"retry_after": null} must fall back to the default: float(None)
    raises TypeError, which escaped post()'s errors-as-values contract
    before the except was widened."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
    repo = DiscordWebhookRepo(
        session=_session([_resp(429, json_data={"retry_after": None}), _resp(204)])
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert repo.session.post.call_count == 2


def test_embed_rejects_oversized_field_value():
    """Legacy posted 50 joined RSNs with no limit check and Discord 400'd;
    oversized embeds must fail at construction, not silently in transport."""
    with pytest.raises(Exception):
        Embed(
            title="t",
            fields=[{"name": "n", "value": "x" * 1025}],
        )


def test_embed_rejects_oversized_total():
    fields = [{"name": "n", "value": "x" * 1024} for _ in range(6)]
    with pytest.raises(Exception):
        Embed(title="t", fields=fields)
