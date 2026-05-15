from unittest.mock import AsyncMock, MagicMock

import pytest

from bot_detector.database.api.repository import ApiUserRepo
from bot_detector.database.api.structs import ApiUserTableStruct


@pytest.fixture
def repo():
    return ApiUserRepo()


@pytest.fixture
def session():
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=ctx)
    return session


def _sample_user(
    username: str = "testuser", is_active: bool = True
) -> ApiUserTableStruct:
    return ApiUserTableStruct(
        username=username,
        token="testtoken",
        is_active=is_active,
        ratelimit=100,
    )


def _mock_scalar(result_value):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = result_value
    return mock_result


@pytest.mark.asyncio
async def test_get_by_username_returns_user_when_active(repo, session):
    user = _sample_user()
    session.execute = AsyncMock(return_value=_mock_scalar(user))

    result = await repo.get_by_username(session, "testuser")

    assert result == user


@pytest.mark.asyncio
async def test_get_by_username_returns_none_when_not_found(repo, session):
    session.execute = AsyncMock(return_value=_mock_scalar(None))

    result = await repo.get_by_username(session, "nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_get_by_username_returns_none_when_inactive(repo, session):
    session.execute = AsyncMock(return_value=_mock_scalar(None))

    result = await repo.get_by_username(session, "inactiveuser")

    assert result is None


@pytest.mark.asyncio
async def test_log_usage_inserts_row(repo, session):
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    await repo.log_usage(session, 1, "/api/feedback")

    session.execute.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_log_usage_auto_commits_by_default(repo, session):
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    await repo.log_usage(session, 1, "/api/feedback")

    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_log_usage_skips_commit_when_disabled(repo, session):
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    await repo.log_usage(session, 1, "/api/feedback", auto_commit=False)

    session.execute.assert_called_once()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_has_permission_returns_true_when_found(repo, session):
    session.execute = AsyncMock(return_value=_mock_scalar(MagicMock()))

    result = await repo.has_permission(session, user_name="testuser", permission="request_highscores")

    assert result is True


@pytest.mark.asyncio
async def test_has_permission_returns_false_when_not_found(repo, session):
    session.execute = AsyncMock(return_value=_mock_scalar(None))

    result = await repo.has_permission(session, user_name="testuser", permission="nonexistent_perm")

    assert result is False


@pytest.mark.asyncio
async def test_has_permission_returns_false_when_user_not_exists(repo, session):
    session.execute = AsyncMock(return_value=_mock_scalar(None))

    result = await repo.has_permission(session, user_name="ghost", permission="request_highscores")

    assert result is False
