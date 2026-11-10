from bot_detector.firehose.api.me import firehose_topics
from bot_detector.firehose.app.consumer import ALLOWED_TOPICS


def test_reports_topic_is_not_advertised():
    # reports.to_insert is disabled: the catalog is the single source of
    # truth for /firehose/topics and the websocket 4404 gate
    assert "reports.to_insert" not in ALLOWED_TOPICS


def test_legacy_reports_scope_projects_to_no_topics():
    # a keyed user whose stored scope predates the disable sees no topics
    assert firehose_topics(scopes=["firehose.reports.to_insert"]) == []


def test_wildcard_scope_excludes_disabled_topic():
    assert "reports.to_insert" not in firehose_topics(scopes=["firehose.*"])
