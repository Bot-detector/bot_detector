import asyncio

import pytest

from bases.api_public.core.fastapi.dependencies.to_jagex_name import to_jagex_name
from bases.api_public.player.repository import Player
from bases.api_public.core._cache import SimpleALRUCache


class _DummySession:
    async def execute(self, *args, **kwargs):  # pragma: no cover - not used here
        raise AssertionError("execute should not be called")


@pytest.mark.asyncio()
async def test_to_jagex_name_normalizes_variants():
    assert await to_jagex_name("Some_Name") == "some name"
    assert await to_jagex_name("AlreadyClean") == "alreadyclean"


def test_player_sanitize_name_is_consistent():
    repo = Player(session=_DummySession(), cache=SimpleALRUCache())
    assert repo.sanitize_name("My_Name-Here  ") == "my name here"
