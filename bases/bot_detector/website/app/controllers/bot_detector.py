import aiohttp


class BotDetector:
    def __init__(
        self, token: str, base_url: str = "https://api.prd.osrsbotdetector.com"
    ):
        self.base_url = base_url
        self.session = aiohttp.ClientSession()
        self.token = token

    async def get_prediction(self, name: str) -> list:
        url = f"{self.base_url}/v2/player/prediction"
        params = {"name": name, "breakdown": "true"}
        async with self.session.get(url, params=params) as response:
            if response.status == 404:
                return []
            response.raise_for_status()
            data: list = await response.json()
            return data

    async def get_project_stats(self):
        url = f"{self.base_url}/site/dashboard/projectstats"
        async with self.session.get(url) as response:
            data = await response.json()
            return data
