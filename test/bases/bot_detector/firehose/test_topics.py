from bot_detector.firehose.api.me import firehose_topics
from bot_detector.firehose.app.consumer import (
    ALLOWED_TOPICS,
    anonymous_topics,
    keyed_only_topics,
)
from bot_detector.firehose.core.config import Settings

REPORTS = "reports.to_insert"


def test_settings_default_makes_reports_keyed_only():
    # the product default: raw user reports are not anonymous-visible;
    # every other catalog topic is public
    assert Settings().topic_access == {REPORTS: "keyed"}


def test_resolvers_split_the_catalog_by_access():
    access = {REPORTS: "keyed"}
    keyed_only = keyed_only_topics(topic_access=access)

    assert keyed_only == {REPORTS}
    assert REPORTS not in anonymous_topics(
        allowed_topics=ALLOWED_TOPICS, keyed_only=keyed_only
    )
    assert "players.scraped" in anonymous_topics(
        allowed_topics=ALLOWED_TOPICS, keyed_only=keyed_only
    )


def test_public_mode_returns_the_topic_to_anonymous():
    # the toggle: flipping a topic to public (or dropping it from the
    # map) puts it back into the anonymous-visible list
    access = {REPORTS: "public"}
    keyed_only = keyed_only_topics(topic_access=access)

    assert keyed_only == frozenset()
    assert REPORTS in anonymous_topics(
        allowed_topics=ALLOWED_TOPICS, keyed_only=keyed_only
    )


def test_legacy_reports_scope_projects_to_the_topic():
    # keyed visibility is the catalog intersected with scopes, so a
    # keyed identity keeps reports even while it is keyed-only
    assert firehose_topics(scopes=["firehose.reports.to_insert"]) == [REPORTS]


def test_wildcard_scope_includes_keyed_only_topic():
    assert REPORTS in firehose_topics(scopes=["firehose.*"])
