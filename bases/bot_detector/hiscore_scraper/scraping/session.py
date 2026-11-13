from aiohttp import ClientSession, DummyCookieJar, TCPConnector


def build_session(connector_limit: int | None = None) -> ClientSession:
    """Builds the scraper session.

    Cookie-free on purpose: Jagex's edge redirects to the community page
    (hiscores "down" page) when its tracking cookies are echoed back, so the
    session must never send cookies.

    Args:
        connector_limit: total connection cap for the shared session. The
            fetch pool holds many requests in flight per session, so it must
            exceed aiohttp's default limit (100) or the connector binds
            before the pool does.
    """
    connector = TCPConnector(limit=connector_limit) if connector_limit else None
    return ClientSession(
        headers={"User-Agent": "http://osrsbotdetector.com"},
        cookie_jar=DummyCookieJar(),
        connector=connector,
    )
