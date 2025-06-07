import asyncio

import httpx
import pytest


@pytest.mark.asyncio
async def test_highscore_v2(benchmark, custom_client):
    player_ids = list(range(1, 101))  # Or any other player IDs you want to use
    async with httpx.AsyncClient() as client:

        async def request(player_id):
            endpoint = "http://localhost:5000/v2/highscore/latest"
            params = {"player_id": player_id}
            response = await client.get(url=endpoint, params=params)
            return response

        async def run_requests():
            tasks = [
                asyncio.create_task(request(player_id)) for player_id in player_ids
            ]
            return await asyncio.gather(*tasks)

        _ = await benchmark(run_requests)


@pytest.mark.asyncio
async def test_highscore_v3(benchmark, custom_client):
    player_ids = list(range(1, 101))  # Or any other player IDs you want to use
    async with httpx.AsyncClient() as client:

        async def request(player_id):
            endpoint = "http://localhost:5000/v3/highscore/latest"
            params = {"player_id": player_id}
            response = await client.get(url=endpoint, params=params)
            return response

        async def run_requests():
            tasks = [
                asyncio.create_task(request(player_id)) for player_id in player_ids
            ]
            return await asyncio.gather(*tasks)

        _ = await benchmark(run_requests)
