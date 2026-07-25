from unittest.mock import AsyncMock, MagicMock

import pytest

from bot_detector.database.api_public.feedback import FeedbackRepo
from bot_detector.database.api_public.label import LabelRepo
from bot_detector.database.api_public.player import PlayerRepo


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock().__aenter__())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


class TestPlayerRepoSanitizeName:
    def test_lowercase(self):
        assert PlayerRepo.sanitize_name("TestPlayer") == "testplayer"

    def test_underscores_to_spaces(self):
        assert PlayerRepo.sanitize_name("test_player") == "test player"

    def test_dashes_to_spaces(self):
        assert PlayerRepo.sanitize_name("test-player") == "test player"

    def test_strips_whitespace(self):
        assert PlayerRepo.sanitize_name("  test  ") == "test"


class TestPlayerRepoGet:
    @pytest.mark.asyncio
    async def test_get_returns_none_when_no_results(self):
        session = _mock_session()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        repo = PlayerRepo(session)
        player = await repo.get("nonexistent")
        assert player is None

    @pytest.mark.asyncio
    async def test_get_returns_player_when_found(self):
        session = _mock_session()
        fake_player = MagicMock()
        fake_player.name = "testplayer"
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [fake_player]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        repo = PlayerRepo(session)
        player = await repo.get("testplayer")
        assert player is not None
        assert player.name == "testplayer"


class TestPlayerRepoGetOrInsert:
    @pytest.mark.asyncio
    async def test_get_or_insert_returns_existing(self):
        session = _mock_session()
        fake_player = MagicMock()
        fake_player.name = "testplayer"
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [fake_player]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        repo = PlayerRepo(session)
        player = await repo.get_or_insert("testplayer")
        assert player.name == "testplayer"
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_insert_creates_when_missing(self):
        session = _mock_session()

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            scalars_mock = MagicMock()
            if call_count == 1:
                scalars_mock.all.return_value = []
            else:
                fake = MagicMock()
                fake.name = "newplayer"
                scalars_mock.all.return_value = [fake]
            result_mock = MagicMock()
            result_mock.scalars.return_value = scalars_mock
            return result_mock

        session.execute.side_effect = mock_execute

        repo = PlayerRepo(session)
        player = await repo.get_or_insert("newplayer")
        assert player.name == "newplayer"
        assert call_count == 3


class TestPlayerRepoGetReportScore:
    @pytest.mark.asyncio
    async def test_get_report_score_passes_tuple_names(self):
        session = _mock_session()
        mappings_mock = MagicMock()
        mappings_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.mappings.return_value = mappings_mock
        session.execute.return_value = result_mock

        repo = PlayerRepo(session)
        result = await repo.get_report_score(player_names=("player1", "player2"))
        assert result == []

    @pytest.mark.asyncio
    async def test_get_report_score_rejects_non_tuple(self):
        session = _mock_session()
        repo = PlayerRepo(session)
        with pytest.raises(ValueError, match="must be a tuple"):
            await repo.get_report_score(player_names=["player1"])


class TestFeedbackRepo:
    @pytest.mark.asyncio
    async def test_insert_feedback_rejects_missing_voter(self):
        session = _mock_session()
        mappings_mock = MagicMock()
        mappings_mock.first.return_value = None
        result_mock = MagicMock()
        result_mock.mappings.return_value = mappings_mock
        session.execute.return_value = result_mock

        repo = FeedbackRepo(session)
        success, detail = await repo.insert_feedback(
            feedback_data={
                "player_name": "unknown",
                "subject_id": 1,
                "prediction": "Real_Player",
                "confidence": 0.9,
                "vote": 1,
                "feedback_text": None,
                "proposed_label": None,
            }
        )
        assert success is False
        assert detail == "voter_does_not_exist"


class TestLabelRepo:
    @pytest.mark.asyncio
    async def test_get_labels_returns_list(self):
        session = _mock_session()

        fake_label = MagicMock()
        fake_label.id = 1
        fake_label.label = "Real_Player"
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [fake_label]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        repo = LabelRepo(session)
        labels = await repo.get_labels()
        assert len(labels) == 1
        assert labels[0].label == "Real_Player"

    @pytest.mark.asyncio
    async def test_get_label_by_id_returns_none_when_missing(self):
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        repo = LabelRepo(session)
        label = await repo.get_label_by_id(999)
        assert label is None
