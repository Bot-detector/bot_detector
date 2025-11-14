from fastapi.testclient import TestClient

from bases.bot_detector.api_public.core import server
from bases.bot_detector.api_public.core.fastapi.dependencies.session import get_session
from bot_detector.player.services import PlayerService
from bot_detector.feedback.services import FeedbackService
from bot_detector.report.services.reports import CustomError, ReportsService


async def _dummy_session():
    yield object()


def _client(monkeypatch):
    app = server.create_app()
    app.dependency_overrides[get_session] = _dummy_session
    return TestClient(app)


def test_player_prediction_not_found(monkeypatch):
    async def fake_prediction(*args, **kwargs):
        return []

    monkeypatch.setattr(PlayerService, "get_prediction", fake_prediction)
    client = _client(monkeypatch)
    resp = client.get(
        "/v2/player/prediction",
        params={"name": ["abc"], "breakdown": "false"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Player not found"


def test_feedback_duplicate_returns_422(monkeypatch):
    async def fake_insert(*args, **kwargs):
        return False, "duplicate_record"

    monkeypatch.setattr(FeedbackService, "insert_feedback", fake_insert)
    client = _client(monkeypatch)
    payload = {
        "player_name": "abc",
        "vote": 1,
        "prediction": "bot",
        "confidence": 0.5,
        "subject_id": 1,
    }
    resp = client.post("/v2/feedback", json=payload)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "duplicate_record"


def test_report_validation_error(monkeypatch):
    async def fake_parse(self, data):
        return None, "invalid data size"

    monkeypatch.setattr(ReportsService, "parse_data", fake_parse)
    client = _client(monkeypatch)
    resp = client.post("/v2/report", json=[])
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid data size"


def test_report_producer_failure(monkeypatch):
    async def fake_parse(self, data):
        class _Detection:
            reporter = "a"
            reported = "b"

            def model_dump(self):
                return {
                    "reporter": "a",
                    "reported": "b",
                    "region_id": 1,
                    "x_coord": 1,
                    "y_coord": 1,
                    "z_coord": 0,
                    "ts": 1,
                    "manual_detect": 0,
                    "on_members_world": 0,
                    "on_pvp_world": 0,
                    "world_number": 301,
                    "equipment": {
                        "equip_head_id": 1,
                        "equip_amulet_id": 1,
                        "equip_torso_id": 1,
                        "equip_legs_id": 1,
                        "equip_boots_id": 1,
                        "equip_cape_id": 1,
                        "equip_hands_id": 1,
                        "equip_weapon_id": 1,
                        "equip_shield_id": 1,
                    },
                    "equip_ge_value": 1,
                }

        return [_Detection()], None

    class _Player:
        def __init__(self, name, id_):
            self.name = name
            self.id = id_

    async def fake_get_or_insert(self, player_name, **kwargs):
        return _Player(player_name, 1 if player_name == "a" else 2)

    async def fake_send(self, *args, **kwargs):
        raise CustomError("boom")

    monkeypatch.setattr(ReportsService, "parse_data", fake_parse)
    monkeypatch.setattr(PlayerService, "get_or_insert", fake_get_or_insert)
    monkeypatch.setattr(PlayerService, "sanitize_name", lambda self, n: n)
    monkeypatch.setattr(ReportsService, "send_to_kafka", fake_send)

    client = _client(monkeypatch)
    resp = client.post(
        "/v2/report",
        json=[
            {
                "reporter": "a",
                "reported": "b",
                "region_id": 1,
                "x_coord": 1,
                "y_coord": 1,
                "z_coord": 0,
                "ts": 1,
                "manual_detect": 0,
                "on_members_world": 0,
                "on_pvp_world": 0,
                "world_number": 301,
                "equipment": {
                    "equip_head_id": 1,
                    "equip_amulet_id": 1,
                    "equip_torso_id": 1,
                    "equip_legs_id": 1,
                    "equip_boots_id": 1,
                    "equip_cape_id": 1,
                    "equip_hands_id": 1,
                    "equip_weapon_id": 1,
                    "equip_shield_id": 1,
                },
                "equip_ge_value": 1,
            }
        ],
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal error"


def test_player_prediction_success(monkeypatch):
    async def fake_prediction(*args, **kwargs):
        return [
            {
                "player_id": 1,
                "name": "abc",
                "created_at": "2024-01-01T00:00:00",
                "model_name": "m",
                "prediction": "bot",
                "confidence": 0.9,
                "predictions": {"bot": 0.9},
            }
        ]

    monkeypatch.setattr(PlayerService, "get_prediction", fake_prediction)
    client = _client(monkeypatch)
    resp = client.get(
        "/v2/player/prediction",
        params={"name": ["abc"], "breakdown": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["player_name"] == "abc"
    assert body[0]["predictions_breakdown"] == {"bot": 0.9}


def test_feedback_success(monkeypatch):
    async def fake_insert(*args, **kwargs):
        return True, "success"

    monkeypatch.setattr(FeedbackService, "insert_feedback", fake_insert)
    client = _client(monkeypatch)
    payload = {
        "player_name": "abc",
        "vote": 1,
        "prediction": "bot",
        "confidence": 0.5,
        "subject_id": 1,
    }
    resp = client.post("/v2/feedback", json=payload)
    assert resp.status_code == 201
    assert resp.json()["detail"] == "success"


def test_report_success(monkeypatch):
    async def fake_parse(self, data):
        class _Detection:
            reporter = "a"
            reported = "b"

            def model_dump(self):
                return {
                    "reporter": "a",
                    "reported": "b",
                    "region_id": 1,
                    "x_coord": 1,
                    "y_coord": 1,
                    "z_coord": 0,
                    "ts": 1,
                    "manual_detect": 0,
                    "on_members_world": 0,
                    "on_pvp_world": 0,
                    "world_number": 301,
                    "equipment": {
                        "equip_head_id": 1,
                        "equip_amulet_id": 1,
                        "equip_torso_id": 1,
                        "equip_legs_id": 1,
                        "equip_boots_id": 1,
                        "equip_cape_id": 1,
                        "equip_hands_id": 1,
                        "equip_weapon_id": 1,
                        "equip_shield_id": 1,
                    },
                    "equip_ge_value": 1,
                }

        return [_Detection()], None

    class _Player:
        def __init__(self, name, id_):
            self.name = name
            self.id = id_

    async def fake_get_or_insert(self, player_name, **kwargs):
        return _Player(player_name, 1 if player_name == "a" else 2)

    async def fake_send(self, *args, **kwargs):
        return None

    monkeypatch.setattr(ReportsService, "parse_data", fake_parse)
    monkeypatch.setattr(PlayerService, "get_or_insert", fake_get_or_insert)
    monkeypatch.setattr(PlayerService, "sanitize_name", lambda self, n: n)
    monkeypatch.setattr(ReportsService, "send_to_kafka", fake_send)

    client = _client(monkeypatch)
    resp = client.post(
        "/v2/report",
        json=[
            {
                "reporter": "a",
                "reported": "b",
                "region_id": 1,
                "x_coord": 1,
                "y_coord": 1,
                "z_coord": 0,
                "ts": 1,
                "manual_detect": 0,
                "on_members_world": 0,
                "on_pvp_world": 0,
                "world_number": 301,
                "equipment": {
                    "equip_head_id": 1,
                    "equip_amulet_id": 1,
                    "equip_torso_id": 1,
                    "equip_legs_id": 1,
                    "equip_boots_id": 1,
                    "equip_cape_id": 1,
                    "equip_hands_id": 1,
                    "equip_weapon_id": 1,
                    "equip_shield_id": 1,
                },
                "equip_ge_value": 1,
            }
        ],
    )
    assert resp.status_code == 201
    assert resp.json()["detail"] == "ok"
