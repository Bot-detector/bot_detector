from bot_detector.public_api import LegacyApiClient, PublicApiClient


def test_sample():
    assert PublicApiClient is not None
    assert LegacyApiClient is not None
