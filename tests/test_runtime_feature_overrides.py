from app.core.lifespan import RuntimeFeatureOverrides


def test_resolve_tracks_override_disable_and_reset() -> None:
    overrides = RuntimeFeatureOverrides()

    assert overrides.resolve("semantic_search_enabled", default=True) is True
    assert overrides.resolve("semantic_search_enabled", default=False) is False

    overrides.semantic_search_enabled = True
    assert overrides.resolve("semantic_search_enabled", default=False) is True

    overrides.semantic_search_enabled = False
    assert overrides.resolve("semantic_search_enabled", default=True) is False

    overrides.semantic_search_enabled = True
    assert overrides.resolve("semantic_search_enabled", default=False) is True
    overrides.disable("semantic_search_enabled")
    assert overrides.semantic_search_enabled is False
    assert overrides.resolve("semantic_search_enabled", default=True) is False

    overrides.semantic_search_enabled = None
    assert overrides.resolve("semantic_search_enabled", default=False) is False
    assert overrides.resolve("semantic_search_enabled", default=True) is True


def test_disable_rejects_unknown_flag_without_changing_known_override() -> None:
    assert RuntimeFeatureOverrides().semantic_search_enabled is None
    unset_overrides = RuntimeFeatureOverrides()
    unset_overrides.disable("semantic_search_enabled")
    if unset_overrides.semantic_search_enabled is not False:
        raise AssertionError("disable_from_none_contract")

    overrides = RuntimeFeatureOverrides(semantic_search_enabled=True)

    try:
        overrides.disable("unknown_runtime_flag")
    except AttributeError as exc:
        if "Unknown runtime flag" not in str(exc):
            raise AssertionError("unknown_flag_error_contract") from None
    else:
        raise AssertionError("unknown_flag_must_be_rejected")

    assert overrides.semantic_search_enabled is True


def test_resolve_returns_supplied_default_for_unknown_flag() -> None:
    overrides = RuntimeFeatureOverrides()

    assert overrides.resolve("unknown_runtime_flag", default=True) is True
    assert overrides.resolve("unknown_runtime_flag", default=False) is False
    assert not hasattr(overrides, "unknown_runtime_flag")
