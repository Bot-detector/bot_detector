import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_one_player_id(custom_client):
    endpoint = "/v2/player"

    async with custom_client as client:
        client: AsyncClient
        params = {"player_id": 1, "greater_than": 0}
        response = await client.get(url=endpoint, params=params)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

        json_response: list[dict] = response.json()
        assert len(json_response) == 1
        assert isinstance(json_response[0], dict)
        player = json_response[0]
        assert player.get("id") == 1


@pytest.mark.asyncio
async def test_one_player_name(custom_client):
    endpoint = "/v2/player"

    async with custom_client as client:
        client: AsyncClient
        params = {"player_name": "Player_0", "greater_than": 0}
        response = await client.get(url=endpoint, params=params)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

        json_response: list[dict] = response.json()
        assert len(json_response) == 1
        assert isinstance(json_response[0], dict)
        player = json_response[0]
        assert player.get("name") == "Player_0"


@pytest.mark.asyncio
async def test_many_player(custom_client):
    endpoint = "/v2/player"

    async with custom_client as client:
        client: AsyncClient
        params = {"player_id": 1, "greater_than": 1}
        response = await client.get(url=endpoint, params=params)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

        json_response: list[dict] = response.json()
        assert len(json_response) > 1
        assert isinstance(json_response[0], dict)
        player = json_response[0]
        assert player.get("id") == 1


@pytest.mark.asyncio
async def test_player_label(custom_client):
    endpoint = "/v2/player"

    async with custom_client as client:
        client: AsyncClient
        params = {"label_id": 0}
        response = await client.get(url=endpoint, params=params)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

        json_response: list[dict] = response.json()
        assert len(json_response) >= 1
        assert isinstance(json_response[0], dict)
