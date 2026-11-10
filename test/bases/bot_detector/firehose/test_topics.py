from bot_detector.firehose.api.me import firehose_topics
from bot_detector.firehose.core.config import Settings

REPORTS = "reports.to_insert"


def test_settings_default_keys_only_reports():
    settings = Settings()
    assert settings.keyed_topics == {REPORTS}
    assert "players.scraped" in settings.public_topics


def test_topic_lists_parse_csv_from_env():
    settings = Settings(
        public_topics="players.scraped, players.not_found",
        keyed_topics="reports.to_insert",
    )
    assert settings.public_topics == {"players.scraped", "players.not_found"}
    assert settings.keyed_topics == {REPORTS}


def test_legacy_reports_scope_projects_to_the_topic():
    topics = firehose_topics(
        scopes=["firehose.reports.to_insert"],
        streamable={REPORTS, "players.scraped"},
    )
    assert topics == [REPORTS]


def test_wildcard_scope_projects_all_streamable_topics():
    topics = firehose_topics(
        scopes=["firehose.*"], streamable={REPORTS, "players.scraped"}
    )
    assert topics == ["players.scraped", REPORTS]
