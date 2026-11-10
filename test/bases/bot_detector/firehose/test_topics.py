from bot_detector.firehose.api.me import firehose_topics
from bot_detector.firehose.app.consumer import ALLOWED_TOPICS
from bot_detector.firehose.core.config import Settings

REPORTS = "reports.to_insert"


def test_settings_defaults_cover_the_catalog_and_key_reports():
    settings = Settings()
    assert settings.public_topics | settings.keyed_topics == set(ALLOWED_TOPICS)
    assert settings.keyed_topics == {REPORTS}


def test_topic_lists_parse_csv_from_env():
    settings = Settings(
        public_topics="players.scraped, players.not_found",
        keyed_topics="reports.to_insert",
    )
    assert settings.public_topics == {"players.scraped", "players.not_found"}
    assert settings.keyed_topics == {REPORTS}


def test_legacy_reports_scope_projects_to_the_topic():
    assert firehose_topics(scopes=["firehose.reports.to_insert"]) == [REPORTS]


def test_wildcard_scope_includes_keyed_only_topic():
    assert REPORTS in firehose_topics(scopes=["firehose.*"])
