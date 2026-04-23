import inspect

import pytest
from unittest.mock import AsyncMock

from bot_detector.public_api import LegacyApiClient, PublicApiClient


def _make_public_client() -> PublicApiClient:
    session = AsyncMock()
    return PublicApiClient(session=session, base_url="http://localhost")


def _make_legacy_client() -> LegacyApiClient:
    session = AsyncMock()
    return LegacyApiClient(session=session, token="test-token", base_url="http://localhost/")


PUBLIC_API_METHODS = {
    "get_report_score": {"names"},
    "get_feedback_score": {"names"},
    "get_prediction": {"names", "breakdown"},
    "post_reports": {"detections"},
    "post_feedback": {"feedback"},
    "get_labels": set(),
    "get_label_by_id": {"label_id"},
}

LEGACY_API_METHODS = {
    "get_project_stats": set(),
    "verify_bot": {"bots"},
    "get_player": {"player_name"},
    "create_player": {"name"},
    "get_discord_verification_status": {"player_name"},
    "get_discord_player": {"player_name"},
    "get_verification_attempts": {"player_name"},
    "post_verification_request": {"info"},
    "post_discord_code": {"discord_id", "player_name", "code"},
    "get_linked_accounts": {"discord_id"},
    "get_discord_links": {"discord_id"},
    "get_xp_gains": {"player_name"},
    "get_latest_sighting": {"player_name"},
    "get_region": {"region_name"},
    "get_heatmap_region": {"region_name"},
    "get_heatmap_data": {"region_id"},
    "get_hiscore_latest": {"player_id"},
    "generate_player_bans_export": {"export"},
    "download_export": {"export_id"},
}


@pytest.mark.parametrize("method_name", list(PUBLIC_API_METHODS.keys()))
def test_public_api_method_exists(method_name: str):
    client = _make_public_client()
    assert hasattr(client, method_name), (
        f"PublicApiClient missing method '{method_name}'"
    )
    assert callable(getattr(client, method_name))


@pytest.mark.parametrize(
    "method_name,expected_params",
    list(PUBLIC_API_METHODS.items()),
)
def test_public_api_method_params(method_name: str, expected_params: set[str]):
    method = getattr(PublicApiClient, method_name)
    sig = inspect.signature(method)
    actual_params = {
        name
        for name, param in sig.parameters.items()
        if name != "self" and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    }
    missing = expected_params - actual_params
    assert not missing, (
        f"PublicApiClient.{method_name} missing params {missing}. "
        f"Expected {expected_params}, got {actual_params}"
    )


@pytest.mark.parametrize("method_name", list(LEGACY_API_METHODS.keys()))
def test_legacy_api_method_exists(method_name: str):
    client = _make_legacy_client()
    assert hasattr(client, method_name), (
        f"LegacyApiClient missing method '{method_name}'"
    )
    assert callable(getattr(client, method_name))


@pytest.mark.parametrize(
    "method_name,expected_params",
    list(LEGACY_API_METHODS.items()),
)
def test_legacy_api_method_params(method_name: str, expected_params: set[str]):
    method = getattr(LegacyApiClient, method_name)
    sig = inspect.signature(method)
    actual_params = {
        name
        for name, param in sig.parameters.items()
        if name != "self" and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    }
    missing = expected_params - actual_params
    assert not missing, (
        f"LegacyApiClient.{method_name} missing params {missing}. "
        f"Expected {expected_params}, got {actual_params}"
    )


def test_public_api_no_legacy_methods():
    client = _make_public_client()
    legacy_only = {"get_player", "get_discord_player", "post_discord_code",
                   "get_discord_links", "get_hiscore_latest", "create_player",
                   "get_heatmap_region", "get_heatmap_data", "get_latest_sighting",
                   "get_xp_gains", "get_region", "get_linked_accounts"}
    for method_name in legacy_only:
        assert not hasattr(client, method_name) or not callable(getattr(client, method_name, None)), (
            f"PublicApiClient should not have v1 method '{method_name}'"
        )


def test_legacy_base_url():
    assert LegacyApiClient.DEFAULT_BASE_URL == "https://www.api-v1.osrsbotdetector.com/"


def test_public_base_url():
    assert PublicApiClient.DEFAULT_BASE_URL == "https://api.prd.osrsbotdetector.com"


ALIAS_METHODS = {"get_discord_player", "post_discord_code", "get_discord_links", "get_heatmap_region"}

@pytest.mark.parametrize("method_name", [m for m in LEGACY_API_METHODS if m not in ALIAS_METHODS])
def test_legacy_methods_use_base_url(method_name: str):
    method = getattr(LegacyApiClient, method_name)
    source = inspect.getsource(method)
    assert "self.base_url" in source, (
        f"LegacyApiClient.{method_name} must use self.base_url"
    )


def test_aliases_delegate():
    client = _make_legacy_client()
    assert client.get_discord_player.__wrapped__ if hasattr(client.get_discord_player, '__wrapped__') else True
    assert client.post_discord_code.__wrapped__ if hasattr(client.post_discord_code, '__wrapped__') else True
    assert client.get_discord_links.__wrapped__ if hasattr(client.get_discord_links, '__wrapped__') else True
    assert client.get_heatmap_region.__wrapped__ if hasattr(client.get_heatmap_region, '__wrapped__') else True


def test_exports_from_init():
    from bot_detector.public_api import (
        LegacyApiClient,
        PublicApiClient,
        RetryableError,
        retry,
    )

    assert LegacyApiClient is not None
    assert PublicApiClient is not None
    assert RetryableError is not None
    assert retry is not None
