from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.database.feedback import FeedbackExportRepo
from bot_detector.structs import FeedbackExportItem


def _mock_session(rows: list[dict]) -> AsyncMock:
    session = AsyncMock()
    mappings_mock = MagicMock()
    mappings_mock.all.return_value = rows
    result_mock = MagicMock()
    result_mock.mappings.return_value = mappings_mock
    session.execute.return_value = result_mock
    return session


@pytest.mark.asyncio
async def test_get_feedback_export_returns_items():
    rows = [
        {
            "subject_name": "player1",
            "is_banned": True,
            "vote": 1,
            "prediction": "bot",
        },
        {
            "subject_name": "player2",
            "is_banned": False,
            "vote": 0,
            "prediction": "human",
        },
    ]
    session = _mock_session(rows)
    repo = FeedbackExportRepo()

    result = await repo.get_feedback_export(session, voter_player_id=42)

    assert len(result) == 2
    assert result[0] == FeedbackExportItem(
        subject_name="player1", is_banned=True, vote=1, prediction="bot"
    )
    assert result[1] == FeedbackExportItem(
        subject_name="player2", is_banned=False, vote=0, prediction="human"
    )


@pytest.mark.asyncio
async def test_get_feedback_export_returns_empty_for_no_feedback():
    session = _mock_session([])
    repo = FeedbackExportRepo()

    result = await repo.get_feedback_export(session, voter_player_id=999)

    assert result == []


@pytest.mark.asyncio
async def test_get_feedback_export_ban_status_false_when_not_banned():
    rows = [
        {
            "subject_name": "player3",
            "is_banned": False,
            "vote": 1,
            "prediction": "bot",
        },
    ]
    session = _mock_session(rows)
    repo = FeedbackExportRepo()

    result = await repo.get_feedback_export(session, voter_player_id=10)

    assert len(result) == 1
    assert result[0].is_banned is False


@pytest.mark.asyncio
async def test_get_feedback_export_multiple_rows_same_voter():
    rows = [
        {
            "subject_name": "player_a",
            "is_banned": True,
            "vote": 1,
            "prediction": "bot",
        },
        {
            "subject_name": "player_a",
            "is_banned": True,
            "vote": 0,
            "prediction": "human",
        },
        {
            "subject_name": "player_b",
            "is_banned": False,
            "vote": 1,
            "prediction": "bot",
        },
    ]
    session = _mock_session(rows)
    repo = FeedbackExportRepo()

    result = await repo.get_feedback_export(session, voter_player_id=5)

    assert len(result) == 3
