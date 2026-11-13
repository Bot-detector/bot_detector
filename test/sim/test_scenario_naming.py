import pkgutil
from importlib.util import find_spec

KNOWN_PREFIXES: frozenset[str] = frozenset(
    {"kafka", "db", "mysql", "scraper", "firehose", "proxy", "jagex"}
)

# the full expected module set: any rename, addition, or removal of a
# scenario module must land here too, or this file fails loudly
EXPECTED_MODULES: frozenset[str] = frozenset(
    {
        "db_insert_storm",
        "firehose_join_storm",
        "firehose_keyed",
        "firehose_parity",
        "firehose_reports_delay",
        "kafka_drain_1m",
        "kafka_smoke",
        "scraper_throughput",
    }
)


def _scenario_dir() -> list[str]:
    """Package search paths of dst.scenarios."""
    spec = find_spec("dst.scenarios")
    assert spec is not None, "dst.scenarios is not importable"
    locations = spec.submodule_search_locations
    assert locations is not None, "dst.scenarios is not a package"
    return list(locations)


def _scenario_modules() -> frozenset[str]:
    """Top-level module names in dst/scenarios/ (subpackages excluded)."""
    names = [
        name
        for _importer, name, is_pkg in pkgutil.iter_modules(_scenario_dir())
        if not is_pkg
    ]
    assert len(names) > 0, "dst/scenarios/ contains no modules"
    return frozenset(names)


def _is_valid_scenario_name(name: str) -> bool:
    """True when name is <known_prefix>_<non-empty scenario>."""
    prefix, sep, scenario = name.partition("_")
    has_known_prefix = prefix in KNOWN_PREFIXES
    has_scenario_part = bool(sep) and bool(scenario)
    return has_known_prefix and has_scenario_part


def test_expected_modules_match_disk():
    on_disk = _scenario_modules()
    missing = EXPECTED_MODULES - on_disk
    extra = on_disk - EXPECTED_MODULES
    assert missing == set(), f"scenario modules removed or renamed: {sorted(missing)}"
    assert extra == set(), f"unexpected scenario modules on disk: {sorted(extra)}"


def test_every_scenario_module_follows_convention():
    for name in sorted(_scenario_modules()):
        assert _is_valid_scenario_name(name), (
            f"{name}: must be <system|component|base>_<scenario> "
            f"with prefix in {sorted(KNOWN_PREFIXES)}"
        )


def test_convention_rejects_unprefixed_names():
    for bad in ("keyed", "join_storm", "reports_delay", "firehose", "smoke"):
        assert not _is_valid_scenario_name(bad), (
            f"{bad}: missing a known system/component prefix"
        )


def test_convention_accepts_current_shapes():
    for good in (
        "kafka_smoke",
        "kafka_drain_1m",
        "db_insert_storm",
        "firehose_join_storm",
        "scraper_throughput",
    ):
        assert _is_valid_scenario_name(good), f"{good}: expected to be valid"
