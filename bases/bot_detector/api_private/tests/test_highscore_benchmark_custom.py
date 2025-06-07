import random
import statistics

import pytest
from benchmark import Benchmark
from httpx import AsyncClient

# Global variable to store the results
benchmark_results = {"v2": [], "v3": []}
player_ids = [random.randint(1, 250) for i in range(10)]
ITERATIONS = 1


async def request(client: AsyncClient, endpoint: str, player_id: int):
    params = {"player_id": player_id, "many": 1, "limit": 5000}
    response = await client.get(url=endpoint, params=params)
    return response


async def bench(iterations, client, endpoint, player_ids):
    for _ in range(iterations):
        for player_id in player_ids:
            async with Benchmark("requests", suppress_logging=True) as b:
                await request(client, endpoint, player_id)
    return b


@pytest.mark.asyncio
async def test_highscore_custom_benchmark_v2(custom_client):
    # Clear the results from the previous tests
    Benchmark.results.clear()
    endpoint = "/v2/highscore/latest"
    async with custom_client as client:
        client: AsyncClient
        b = await bench(ITERATIONS, client, endpoint, player_ids)
    for name, duration in b.results:
        benchmark_results["v2"].append(duration)


@pytest.mark.asyncio
async def test_highscore_custom_benchmark_v3(custom_client):
    # Clear the results from the previous tests
    Benchmark.results.clear()
    endpoint = "/v3/highscore/latest"
    async with custom_client as client:
        client: AsyncClient
        b = await bench(ITERATIONS, client, endpoint, player_ids)
    for name, duration in b.results:
        benchmark_results["v3"].append(duration)


def test_output_results():
    print("v2 results:")
    avg_time = statistics.mean(benchmark_results["v2"])
    median_time = statistics.median(benchmark_results["v2"])
    stdev_time = (
        statistics.stdev(benchmark_results["v2"])
        if len(benchmark_results["v2"]) > 1
        else 0  # if length of results empty return 0
    )
    max_time = max(benchmark_results["v2"])
    min_time = min(benchmark_results["v2"])
    print(
        f"average {avg_time:.3f} seconds, median {median_time:.3f} seconds, stdev {stdev_time:.3f} seconds, max {max_time:.3f} seconds, min {min_time:.3f} seconds"
    )
    assert avg_time > 0

    print("v3 results:")
    avg_time = statistics.mean(benchmark_results["v3"])
    median_time = statistics.median(benchmark_results["v3"])
    stdev_time = (
        statistics.stdev(benchmark_results["v3"])
        if len(benchmark_results["v3"]) > 1
        else 0
    )
    max_time = max(benchmark_results["v3"])
    min_time = min(benchmark_results["v3"])
    print(
        f"average {avg_time:.3f} seconds, median {median_time:.3f} seconds, stdev {stdev_time:.3f} seconds, max {max_time:.3f} seconds, min {min_time:.3f} seconds"
    )
    assert avg_time > 0
