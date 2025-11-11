from fastapi.routing import APIRoute

from bases.api_public import routes


def _api_paths() -> set[str]:
    return {
        route.path
        for route in routes.router.routes
        if isinstance(route, APIRoute)
    }


def test_router_registers_all_feature_paths():
    expected = {
        "/v2/player/report/score",
        "/v2/player/feedback/score",
        "/v2/player/prediction",
        "/v2/report",
        "/v2/feedback",
        "/v2/labels",
        "/v2/labels/{label_id}",
    }
    paths = _api_paths()
    assert expected.issubset(paths)


def test_router_applies_v2_prefix_once():
    paths = _api_paths()
    assert paths, "router should expose routes"
    assert all(path.startswith("/v2/") for path in paths)
