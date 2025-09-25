from typing import Any

import aiohttp


class MLApiClient:
    """
    Async Python client for the Bot-Detector-API (using aiohttp)
    """

    def __init__(self, base_url: str, session: aiohttp.ClientSession):
        """
        Initialize the API client.

        :param base_url: Base URL of the Bot-Detector-API
        """
        self.base_url = base_url.rstrip("/")
        self._session = session

    async def _handle_response(self, response: aiohttp.ClientResponse) -> Any:
        """
        Handle API responses, raising an error if the request failed.
        """
        if response.status >= 400:
            text = await response.text()
            raise RuntimeError(f"API request failed: {response.status} - {text}")
        if response.content_type == "application/json":
            return await response.json()
        return await response.text()

    async def root(self) -> dict[str, Any]:
        """
        GET /
        Root endpoint
        """
        url = f"{self.base_url}/"
        async with self._session.get(url) as resp:
            return await self._handle_response(resp)

    async def health(self) -> dict[str, Any]:
        """
        GET /v1/health
        Check API health
        """
        url = f"{self.base_url}/v1/health"
        async with self._session.get(url) as resp:
            return await self._handle_response(resp)

    async def list_models(self) -> list[str]:
        """
        GET /v1/models
        List all available models
        """
        url = f"{self.base_url}/v1/models"
        async with self._session.get(url) as resp:
            return await self._handle_response(resp)

    async def get_model_info(self, model_name: str) -> dict[str, Any]:
        """
        GET /v1/models/{model_name}
        Retrieve metadata about a specific model.
        """
        url = f"{self.base_url}/v1/models/{model_name}"
        async with self._session.get(url) as resp:
            return await self._handle_response(resp)

    async def predict(
        self, model_name: str, data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        POST /v1/models/{model_name}/predict
        Run predictions using a specific model.

        :param model_name: Name of the model
        :param data: List of dicts representing input features
        """
        url = f"{self.base_url}/v1/models/{model_name}/predict"
        async with self._session.post(url, json=data) as resp:
            return await self._handle_response(resp)
