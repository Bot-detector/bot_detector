from aiohttp import ClientSession, DummyCookieJar


def build_session() -> ClientSession:
    """Builds the scraper session.

    Cookie-free on purpose: Jagex's edge redirects to the community page
    (hiscores "down" page) when its tracking cookies are echoed back, so the
    session must never send cookies.
    """
    return ClientSession(
        headers={"User-Agent": "http://osrsbotdetector.com"},
        cookie_jar=DummyCookieJar(),
    )
