import os
from datetime import datetime, timedelta

import pytest
from bot_detector.runemetrics_api.core import (
    RuneMetricsError,
    RuneMetricsResponse,
)
from bot_detector.runemetrics_scraper import core
from bot_detector.structs import PlayerStruct
from pydantic import BaseModel

os.environ["ENVIRONMENT"] = "test"


class DummyError(BaseModel):
    error: str
    loggedIn: bool = False


@pytest.fixture
def player_struct():
    return PlayerStruct(
        id=1,
        name="test_player",
        created_at=datetime.now() - timedelta(days=1),
        updated_at=None,
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=False,
        label_id=0,
        label_jagex=0,
        ironman=None,
        hardcore_ironman=None,
        ultimate_ironman=None,
        normalized_name=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_value,expected_label",
    [
        (None, 0),
        ("NO_PROFILE", 1),
        ("NOT_A_MEMBER", 2),
        ("PROFILE_PRIVATE", 3),
        ("SOMETHING_ELSE", 0),
    ],
)
async def test_update_player(player_struct: PlayerStruct, error_value, expected_label):
    runemetrics_response = RuneMetricsResponse()

    if error_value is not None:
        runemetrics_response.error = RuneMetricsError(
            error=error_value,
            loggedIn=False,
        )

    updated = await core.update_player(
        player_data=player_struct.model_copy(),
        runemetrics_response=runemetrics_response,
    )

    assert updated.label_jagex == expected_label
    assert updated.possible_ban == 1
    assert updated.confirmed_player == 0
    assert isinstance(updated.updated_at, datetime)


def test_sample():
    assert core is not None
