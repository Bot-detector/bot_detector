import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://test:test@localhost/test")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

from bot_detector.api_public.src.app.report import ReportService
from bot_detector.structs import Detection, Equipment


def _make_detection(**overrides) -> Detection:
    defaults = dict(
        reporter="testreporter",
        reported="testreported",
        region_id=0,
        x_coord=0,
        y_coord=0,
        z_coord=0,
        ts=int(time.time()),
        manual_detect=0,
        on_members_world=0,
        on_pvp_world=0,
        world_number=500,
        equipment=Equipment(),
        equip_ge_value=0,
    )
    defaults.update(overrides)
    return Detection(**defaults)


@pytest.mark.asyncio
async def test_report_service_parse_data_uses_fn_key_on_data_size_error():
    with patch(
        "bot_detector.api_public.src.app.report.wide_event"
    ) as mock_we:
        service = ReportService()
        detections = [_make_detection() for _ in range(5001)]
        await service.parse_data(detections)
        mock_we.add_context.assert_any_call(
            {"parse_data": {"status": "error", "detail": "invalid data size"}}
        )


@pytest.mark.asyncio
async def test_report_service_parse_data_uses_fn_key_on_time_error():
    with patch(
        "bot_detector.api_public.src.app.report.wide_event"
    ) as mock_we:
        service = ReportService()
        detections = [_make_detection(ts=int(time.time()) - 30000)]
        await service.parse_data(detections)
        mock_we.add_context.assert_any_call(
            {"parse_data": {"status": "error", "detail": "invalid time"}}
        )


@pytest.mark.asyncio
async def test_report_service_parse_data_uses_fn_key_on_reporter_error():
    with patch(
        "bot_detector.api_public.src.app.report.wide_event"
    ) as mock_we:
        service = ReportService()
        detections = [
            _make_detection(reporter="reporter_a"),
            _make_detection(reporter="reporter_b"),
        ]
        await service.parse_data(detections)
        mock_we.add_context.assert_any_call(
            {"parse_data": {"status": "error", "detail": "invalid unique reporter"}}
        )


@pytest.mark.asyncio
async def test_report_service_filter_valid_time_uses_fn_key():
    with patch(
        "bot_detector.api_public.src.app.report.wide_event"
    ) as mock_we:
        service = ReportService()
        detections = [_make_detection()]
        service._filter_valid_time(detections)
        call_args = mock_we.add_context.call_args[0][0]
        assert "_filter_valid_time" in call_args
        assert "stale_report_count" in call_args["_filter_valid_time"]
        assert "future_report_count" in call_args["_filter_valid_time"]


@pytest.mark.asyncio
async def test_report_service_check_unique_reporter_uses_fn_key():
    with patch(
        "bot_detector.api_public.src.app.report.wide_event"
    ) as mock_we:
        service = ReportService()
        detections = [_make_detection()]
        service._check_unique_reporter(detections)
        call_args = mock_we.add_context.call_args[0][0]
        assert "_check_unique_reporter" in call_args
        assert "reporters" in call_args["_check_unique_reporter"]


@pytest.mark.asyncio
async def test_report_service_send_to_queue_uses_fn_key():
    with patch(
        "bot_detector.api_public.src.app.report.wide_event"
    ) as mock_we:
        service = ReportService()
        parsed = MagicMock()
        parsed.model_dump.return_value = {
            "reported_id": 1,
            "reporter_id": 2,
            "region_id": 0,
            "x_coord": 0,
            "y_coord": 0,
            "z_coord": 0,
            "ts": int(time.time()),
            "manual_detect": 0,
            "on_members_world": 0,
            "on_pvp_world": 0,
            "world_number": 500,
            "equip_ge_value": 0,
        }
        producer = AsyncMock()
        await service.send_to_queue(data=[parsed], producer=producer)
        for call in mock_we.add_context.call_args_list:
            call_args = call[0][0]
            assert "report" not in call_args or "send_to_queue" in call_args


@pytest.mark.asyncio
async def test_player_get_players_kc_adds_entry_and_success_context():
    with (
        patch(
            "bot_detector.api_public.src.api.v2.player.wide_event"
        ) as mock_we,
        patch(
            "bot_detector.api_public.src.api.v2.player.PlayerRepo"
        ) as mock_repo_cls,
        patch(
            "bot_detector.api_public.src.api.v2.player.to_jagex_name",
            side_effect=lambda n: AsyncMock(_return_value=n)() if False else n,
        ),
        patch(
            "bot_detector.api_public.src.api.v2.player.asyncio"
        ) as mock_asyncio,
    ):
        mock_asyncio.gather = AsyncMock(return_value=["player1"])
        mock_repo = MagicMock()
        mock_repo.get_report_score = AsyncMock(return_value=[MagicMock()])
        mock_repo_cls.return_value = mock_repo

        from bot_detector.api_public.src.api.v2.player import get_players_kc

        await get_players_kc(
            name=["player1"],
            session=MagicMock(),
        )

        calls = [c[0][0] for c in mock_we.add_context.call_args_list]
        assert any("get_players_kc" in c and "names" in c["get_players_kc"] for c in calls)
        assert any(
            "get_players_kc" in c
            and c["get_players_kc"].get("status") == "success"
            for c in calls
        )


@pytest.mark.asyncio
async def test_player_get_feedback_score_adds_entry_and_success_context():
    with (
        patch(
            "bot_detector.api_public.src.api.v2.player.wide_event"
        ) as mock_we,
        patch(
            "bot_detector.api_public.src.api.v2.player.PlayerRepo"
        ) as mock_repo_cls,
        patch(
            "bot_detector.api_public.src.api.v2.player.asyncio"
        ) as mock_asyncio,
    ):
        mock_asyncio.gather = AsyncMock(return_value=["player1"])
        mock_repo = MagicMock()
        mock_repo.get_feedback_score = AsyncMock(return_value=[MagicMock()])
        mock_repo_cls.return_value = mock_repo

        from bot_detector.api_public.src.api.v2.player import get_feedback_score

        await get_feedback_score(
            name=["player1"],
            session=MagicMock(),
        )

        calls = [c[0][0] for c in mock_we.add_context.call_args_list]
        assert any("get_feedback_score" in c and "names" in c["get_feedback_score"] for c in calls)
        assert any(
            "get_feedback_score" in c
            and c["get_feedback_score"].get("status") == "success"
            for c in calls
        )


@pytest.mark.asyncio
async def test_player_get_prediction_adds_entry_context():
    with (
        patch(
            "bot_detector.api_public.src.api.v2.player.wide_event"
        ) as mock_we,
        patch(
            "bot_detector.api_public.src.api.v2.player.PlayerRepo"
        ) as mock_repo_cls,
        patch(
            "bot_detector.api_public.src.api.v2.player.asyncio"
        ) as mock_asyncio,
    ):
        mock_asyncio.gather = AsyncMock(return_value=["player1"])
        mock_repo = MagicMock()
        mock_data = MagicMock()
        mock_repo.get_prediction = AsyncMock(return_value=[mock_data])
        mock_repo_cls.return_value = mock_repo

        with patch(
            "bot_detector.api_public.src.api.v2.player.PredictionResponse"
        ) as mock_resp:
            mock_resp.from_data.return_value = MagicMock()
            from bot_detector.api_public.src.api.v2.player import get_prediction

            await get_prediction(
                name=["player1"],
                breakdown=True,
                session=MagicMock(),
            )

        calls = [c[0][0] for c in mock_we.add_context.call_args_list]
        assert any(
            "get_prediction" in c
            and "names" in c["get_prediction"]
            and "breakdown" in c["get_prediction"]
            for c in calls
        )


@pytest.mark.asyncio
async def test_player_get_prediction_adds_error_context_on_not_found():
    with (
        patch(
            "bot_detector.api_public.src.api.v2.player.wide_event"
        ) as mock_we,
        patch(
            "bot_detector.api_public.src.api.v2.player.PlayerRepo"
        ) as mock_repo_cls,
        patch(
            "bot_detector.api_public.src.api.v2.player.asyncio"
        ) as mock_asyncio,
    ):
        mock_asyncio.gather = AsyncMock(return_value=["player1"])
        mock_repo = MagicMock()
        mock_repo.get_prediction = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        from bot_detector.api_public.src.api.v2.player import get_prediction
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await get_prediction(
                name=["player1"],
                breakdown=True,
                session=MagicMock(),
            )

        calls = [c[0][0] for c in mock_we.add_context.call_args_list]
        assert any(
            "get_prediction" in c
            and c["get_prediction"].get("error") == "Player not found"
            for c in calls
        )


@pytest.mark.asyncio
async def test_labels_get_labels_adds_entry_and_success_context():
    with (
        patch(
            "bot_detector.api_public.src.api.v2.labels.wide_event"
        ) as mock_we,
        patch(
            "bot_detector.api_public.src.api.v2.labels.LabelRepo"
        ) as mock_repo_cls,
    ):
        mock_label = MagicMock()
        mock_label.__dict__ = {"label": "Bot", "id": 1}
        mock_repo = MagicMock()
        mock_repo.get_labels = AsyncMock(return_value=[mock_label])
        mock_repo_cls.return_value = mock_repo

        with patch(
            "bot_detector.api_public.src.api.v2.labels.LabelResponse"
        ) as mock_resp:
            instance = MagicMock()
            instance.label = "Bot"
            mock_resp.return_value = instance

            from bot_detector.api_public.src.api.v2.labels import get_labels

            await get_labels(session=MagicMock())

        calls = [c[0][0] for c in mock_we.add_context.call_args_list]
        assert any("get_labels" in c and c["get_labels"] == {} for c in calls)
        assert any(
            "get_labels" in c
            and c["get_labels"].get("status") == "success"
            and "labels_count" in c["get_labels"]
            for c in calls
        )


@pytest.mark.asyncio
async def test_labels_get_label_by_id_adds_entry_and_success_context():
    with (
        patch(
            "bot_detector.api_public.src.api.v2.labels.wide_event"
        ) as mock_we,
        patch(
            "bot_detector.api_public.src.api.v2.labels.LabelRepo"
        ) as mock_repo_cls,
    ):
        mock_label = MagicMock()
        mock_label.__dict__ = {"label": "Bot", "id": 1}
        mock_repo = MagicMock()
        mock_repo.get_label_by_id = AsyncMock(return_value=mock_label)
        mock_repo_cls.return_value = mock_repo

        with patch(
            "bot_detector.api_public.src.api.v2.labels.LabelResponse"
        ) as mock_resp:
            instance = MagicMock()
            instance.label = "Bot"
            mock_resp.return_value = instance

            from bot_detector.api_public.src.api.v2.labels import get_label_by_id

            await get_label_by_id(label_id=1, session=MagicMock())

        calls = [c[0][0] for c in mock_we.add_context.call_args_list]
        assert any(
            "get_label_by_id" in c and c["get_label_by_id"].get("label_id") == 1
            for c in calls
        )
        assert any(
            "get_label_by_id" in c
            and c["get_label_by_id"].get("status") == "success"
            for c in calls
        )


@pytest.mark.asyncio
async def test_labels_get_label_by_id_not_found_context():
    with (
        patch(
            "bot_detector.api_public.src.api.v2.labels.wide_event"
        ) as mock_we,
        patch(
            "bot_detector.api_public.src.api.v2.labels.LabelRepo"
        ) as mock_repo_cls,
    ):
        mock_repo = MagicMock()
        mock_repo.get_label_by_id = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        from bot_detector.api_public.src.api.v2.labels import get_label_by_id

        result = await get_label_by_id(label_id=99, session=MagicMock())

        assert result is None
        calls = [c[0][0] for c in mock_we.add_context.call_args_list]
        assert any(
            "get_label_by_id" in c
            and c["get_label_by_id"].get("status") == "not_found"
            and c["get_label_by_id"].get("label_id") == 99
            for c in calls
        )


def test_user_read_current_user_adds_called_context():
    with patch(
        "bot_detector.api_public.src.api.v2.user.wide_event"
    ) as mock_we:
        mock_user = MagicMock()
        mock_user.username = "testuser"
        mock_user.token = "testtoken"

        from bot_detector.api_public.src.api.v2.user import read_current_user

        read_current_user(user=mock_user)

        mock_we.add_context.assert_called_once_with(
            {"read_current_user": {"status": "called"}}
        )


@pytest.mark.asyncio
async def test_report_post_reports_uses_fn_key():
    with (
        patch(
            "bot_detector.api_public.src.api.v2.report.wide_event"
        ) as mock_we,
        patch(
            "bot_detector.api_public.src.api.v2.report.ReportService"
        ) as mock_svc_cls,
        patch(
            "bot_detector.api_public.src.api.v2.report.PlayerRepo"
        ) as mock_repo_cls,
        patch(
            "bot_detector.api_public.src.api.v2.report._get_or_insert_cached",
            new_callable=AsyncMock,
        ) as mock_cache,
    ):
        from bot_detector.database.api_public import PlayerRepo as RealPlayerRepo

        mock_repo_cls.sanitize_name = RealPlayerRepo.sanitize_name

        detection = _make_detection()
        mock_svc = MagicMock()
        mock_svc.parse_data = AsyncMock(return_value=([detection], None))
        mock_svc.send_to_queue = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        def _make_player(name, pid):
            p = MagicMock()
            p.name = name
            p.id = pid
            return p

        mock_cache.side_effect = lambda repo, cache, name: _make_player(
            name, abs(hash(name))
        )

        from bot_detector.api_public.src.api.v2.report import post_reports

        await post_reports(
            detections=[detection],
            session=MagicMock(),
            report_producer=MagicMock(),
        )

        calls = [c[0][0] for c in mock_we.add_context.call_args_list]
        for call_args in calls:
            assert "post_reports" in call_args
            assert "report" not in call_args or "post_reports" in call_args
