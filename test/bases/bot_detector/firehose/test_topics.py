from bot_detector.firehose.api.me import firehose_topics
from bot_detector.firehose.app.consumer import ALLOWED_TOPICS, keyed_only_topics
from bot_detector.firehose.core.config import Settings

REPORTS = "reports.to_insert"


def anonymous_view(keyed_only: frozenset[str]) -> list[str]:
    """The advertise rule the anonymous surfaces apply (mirror of prod)."""
    return [t for t in ALLOWED_TOPICS if t not in keyed_only]


def test_settings_default_covers_the_catalog_and_keys_reports():
    # the default map must name every catalog topic (create_app
    # refuses partial maps), and reports is the one keyed-only topic
    access = Settings().topic_access
    assert set(access) == set(ALLOWED_TOPICS)
    assert access[REPORTS] == "keyed"


def test_resolvers_split_the_catalog_by_access():
    keyed_only = keyed_only_topics(topic_access={REPORTS: "keyed"})

    assert keyed_only == {REPORTS}
    assert REPORTS not in anonymous_view(keyed_only=keyed_only)


def test_public_mode_returns_the_topic_to_anonymous():
    # the toggle: flipping a topic to public (or dropping it from the
    # map, modulo the coverage check) puts it back into the anonymous view
    keyed_only = keyed_only_topics(topic_access={REPORTS: "public"})

    assert keyed_only == frozenset()
    assert REPORTS in anonymous_view(keyed_only=keyed_only)


def test_legacy_reports_scope_projects_to_the_topic():
    # keyed visibility is the catalog intersected with scopes, so a
    # keyed identity keeps reports even while it is keyed-only
    assert firehose_topics(scopes=["firehose.reports.to_insert"]) == [REPORTS]


def test_wildcard_scope_includes_keyed_only_topic():
    assert REPORTS in firehose_topics(scopes=["firehose.*"])
