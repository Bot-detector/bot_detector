import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import orjson
import pytest
from bot_detector.discord_webhook import DiscordWebhookRepo, Embed
from bot_detector.discord_webhook.core import (
    MAX_RETRY_AFTER_SECONDS,
    POST_TIMEOUT_SECONDS,
)
from bot_detector.discord_webhook.structs import (
    MAX_EMBEDS_PER_MESSAGE,
    MAX_TOTAL_CHARS,
    EmbedField,
)
from pydantic import ValidationError


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
async def test_post_defaults_when_429_body_lacks_retry_after(monkeypatch):
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
    assert orjson.loads(kwargs["data"]) == {
        "embeds": [
            {"title": "t", "color": 0, "fields": [], "description": "d"},
        ],
        "content": "ping",
    }
    assert kwargs["headers"] == {"Content-Type": "application/json"}
    assert kwargs["allow_redirects"] is False


@pytest.mark.asyncio
async def test_post_passes_total_timeout():
    """The 30s total timeout is the hang guard; falling back to session
    defaults would let a stuck endpoint park the broadcast."""
    resp = _resp(204)
    session = MagicMock(post=MagicMock(return_value=resp))
    repo = DiscordWebhookRepo(session=session)

    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])

    assert err is None
    timeout = session.post.call_args.kwargs["timeout"]
    assert timeout.total == POST_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_post_caps_hostile_retry_after(monkeypatch):
    """A hostile or honest-huge 429 (Discord's shared-limit example is
    1336.57s) must cost cap x attempts, not park the broadcast run past
    its cron window."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    repo = DiscordWebhookRepo(
        session=_session(
            [_resp(429, json_data={"retry_after": 86_400.0}) for _ in range(3)]
        )
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert isinstance(err, Exception)
    assert sleeps == [MAX_RETRY_AFTER_SECONDS, MAX_RETRY_AFTER_SECONDS]


@pytest.mark.asyncio
async def test_post_clamps_negative_retry_after_to_zero(monkeypatch):
    """A negative retry_after would make asyncio.sleep return immediately,
    turning the retry loop into a tight hammer on the endpoint."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    repo = DiscordWebhookRepo(
        session=_session([_resp(429, json_data={"retry_after": -5.0}), _resp(204)])
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert sleeps == [0.0]


@pytest.mark.asyncio
async def test_post_survives_html_429_body(monkeypatch):
    """A proxy returning an HTML 429 makes json() raise ContentTypeError;
    the Retry-After header must still carry the retry."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    resp = _resp(429, headers={"Retry-After": "0.5"})
    resp.json = AsyncMock(side_effect=aiohttp.ContentTypeError(MagicMock(), ()))
    repo = DiscordWebhookRepo(session=_session([resp, _resp(204)]))
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert sleeps == [0.5]


@pytest.mark.asyncio
async def test_post_prefers_body_retry_after_over_header(monkeypatch):
    """Discord's body retry_after is fractional (64.57) and the header is
    its integer ceiling (65) - body-first always waits the shorter, exact
    time the docs' examples show."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    repo = DiscordWebhookRepo(
        session=_session(
            [
                _resp(
                    429,
                    json_data={"retry_after": 1.5},
                    headers={"Retry-After": "9"},
                ),
                _resp(204),
            ]
        )
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert sleeps == [1.5]


@pytest.mark.asyncio
async def test_post_uses_header_when_body_retry_after_is_null(monkeypatch):
    """A garbled body value (null) must not mask a valid Retry-After header."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    repo = DiscordWebhookRepo(
        session=_session(
            [
                _resp(
                    429,
                    json_data={"retry_after": None},
                    headers={"Retry-After": "0.75"},
                ),
                _resp(204),
            ]
        )
    )
    err = await repo.post(url="http://hook", embeds=[Embed(title="t")])
    assert err is None
    assert sleeps == [0.75]


@pytest.mark.asyncio
async def test_post_rejects_more_embeds_than_discord_allows():
    """Discord 400s past 10 embeds; refusing locally fails fast instead of
    trading a transport round-trip for an error value."""
    session = MagicMock(post=MagicMock())
    repo = DiscordWebhookRepo(session=session)
    err = await repo.post(
        url="http://hook",
        embeds=[Embed(title="t") for _ in range(MAX_EMBEDS_PER_MESSAGE + 1)],
    )
    assert isinstance(err, Exception)
    assert str(MAX_EMBEDS_PER_MESSAGE) in str(err)
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_post_refuses_empty_payload():
    """Discord 400s an empty message; the error should name the actual
    problem instead of coming back as an opaque 400 body."""
    session = MagicMock(post=MagicMock())
    repo = DiscordWebhookRepo(session=session)
    err = await repo.post(url="http://hook")
    assert isinstance(err, Exception)
    session.post.assert_not_called()


def test_embed_rejects_naive_timestamp():
    """astimezone() treats naive datetimes as system-local time; a naive
    timestamp would silently shift the embed on the wire."""
    with pytest.raises(Exception):
        Embed(title="t", timestamp=datetime(2026, 1, 1))


@pytest.mark.asyncio
async def test_post_refuses_message_total_over_discord_limit():
    """The 6000-char limit binds per message across all embeds, not per
    embed (Discord docs: "across all embeds attached to a message"): two
    individually valid embeds can still total past the limit."""
    session = MagicMock(post=MagicMock())
    repo = DiscordWebhookRepo(session=session)
    half = Embed(title="t", description="d" * 3500)
    err = await repo.post(url="http://hook", embeds=[half, half])
    assert isinstance(err, Exception)
    assert str(MAX_TOTAL_CHARS) in str(err)
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_post_refuses_message_total_at_boundary():
    """Exactly 6000 chars must pass: the docs measure inclusively."""
    session = MagicMock(post=MagicMock(return_value=_resp(204)))
    repo = DiscordWebhookRepo(session=session)
    # 256 title + 4096 description + (1 name + 1024 value) + (1 name + 622 value)
    exact = Embed(
        title="t" * 256,
        description="d" * 4096,
        fields=[
            EmbedField(name="n", value="x" * 1024),
            EmbedField(name="n", value="x" * 622),
        ],
    )
    assert exact.char_count() == MAX_TOTAL_CHARS
    err = await repo.post(url="http://hook", embeds=[exact])
    assert err is None
    session.post.assert_called_once()


def test_embed_is_frozen():
    """Validators bind at construction only - freezing the model turns
    post-construction mutation into a loud error instead of a silent
    bypass of the size limits."""
    embed = Embed(title="t", fields=[{"name": "n", "value": "v"}])
    assert isinstance(embed.fields, tuple)
    with pytest.raises(ValidationError):
        embed.title = "x" * 300
    with pytest.raises(AttributeError):
        embed.fields.append(EmbedField(name="n", value="v"))


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
