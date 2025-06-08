import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_one_hs_id_v3(custom_client):
    endpoint = "/v3/highscore/latest"
    async with custom_client as client:
        client: AsyncClient
        params = {
            "player_id": 1,
        }
        response = await client.get(url=endpoint, params=params)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

        json_response: list[dict] = response.json()
        assert len(json_response) == 1
        assert isinstance(
            json_response[0], dict
        ), f"expected dict, got {type(json_response[0])}, {json_response=}"

        player = json_response[0]
        assert player.get("player_id") == 1, f"expected id: 1 got: {player=}"


@pytest.mark.asyncio
async def test_many_hs_id_v3(custom_client):
    endpoint = "/v3/highscore/latest"
    async with custom_client as client:
        client: AsyncClient
        params = {"player_id": 1, "many": 1}
        response = await client.get(url=endpoint, params=params)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

        json_response: list[dict] = response.json()
        assert len(json_response) >= 1
        assert isinstance(
            json_response[0], dict
        ), f"expected dict, got {type(json_response[0])}, {json_response=}"

        player = json_response[0]
        assert player.get("player_id") == 1, f"expected id: 1 got: {player=}"


@pytest.mark.asyncio
async def test_highscore_latest_v3(custom_client):
    # TODO: discuss how we are going to test the "keys"
    endpoint = "/v3/highscore/latest"
    async with custom_client as client:
        client: AsyncClient
        params = {"player_id": 1}
        response = await client.get(url=endpoint, params=params)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

        json_response: list[dict] = response.json()
        assert len(json_response) == 1
        assert isinstance(
            json_response[0], dict
        ), f"expected dict, got {type(json_response[0])}, {json_response=}"
