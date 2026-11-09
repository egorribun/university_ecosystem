"""Contracts for the merged production Compose secret environment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
_BASE_COMPOSE_PATH = ROOT / "docker-compose.yml"
_PRODUCTION_COMPOSE_PATH = ROOT / "docker-compose.prod.yml"


class _ComposeReset:
    """Keep Compose's !reset tag so sequence merge semantics stay explicit."""

    def __init__(self, value: Any) -> None:
        self.value = value


class _ComposeOverride:
    """Preserve explicit replacement rather than ordinary Compose merging."""

    def __init__(self, value: Any) -> None:
        self.value = value


class _ComposeLoader(yaml.SafeLoader):
    pass


def _construct_tagged_value(loader: _ComposeLoader, node: yaml.Node) -> Any:
    if isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    elif node.style is not None:
        value = loader.construct_scalar(node)
    else:
        value = yaml.safe_load(loader.construct_scalar(node))
    return value


def _construct_reset(loader: _ComposeLoader, node: yaml.Node) -> _ComposeReset:
    return _ComposeReset(_construct_tagged_value(loader, node))


def _construct_override(loader: _ComposeLoader, node: yaml.Node) -> _ComposeOverride:
    return _ComposeOverride(_construct_tagged_value(loader, node))


_ComposeLoader.add_constructor("!reset", _construct_reset)
_ComposeLoader.add_constructor("!override", _construct_override)


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    raise AssertionError("could not locate the repository Compose files")


def _compose(relative_path: str | Path) -> dict[str, Any]:
    # Parse checked-in YAML only. Do not load .env or evaluate shell
    # interpolation; those sources can contain real deployment credentials.
    compose_path = (
        relative_path
        if isinstance(relative_path, Path)
        else _repo_root() / relative_path
    )
    loader = _ComposeLoader(compose_path.read_text(encoding="utf-8"))
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _normalized_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _merged_env_files(
    base_service: dict[str, Any], production_service: dict[str, Any]
) -> list[Any]:
    base_files = _normalized_sequence(base_service.get("env_file"))
    override_files = production_service.get("env_file")
    if isinstance(override_files, _ComposeReset):
        return []
    if isinstance(override_files, _ComposeOverride):
        return _normalized_sequence(override_files.value)
    if override_files is None:
        return base_files
    # Compose appends ordinary sequence values. Production must use !reset to
    # remove an inherited development env_file.
    return [*base_files, *_normalized_sequence(override_files)]


def _merged_environment(
    base_service: dict[str, Any], production_service: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(base_service.get("environment") or {})
    override = production_service.get("environment")
    if isinstance(override, _ComposeReset):
        return {}
    if isinstance(override, _ComposeOverride):
        merged = {}
        override = override.value
    for key, value in (override or {}).items():
        if isinstance(value, _ComposeReset):
            value = None
        elif isinstance(value, _ComposeOverride):
            value = value.value
        if value is None:
            # Compose null and reset-null values are unset in the container.
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


_PRODUCTION_FILE_SECRETS = {
    "backend": {
        "DATABASE_URL": "/run/secrets/database_url",
        "SECRET_KEY": "/run/secrets/secret_key",
        "NATS_AUTH_TOKEN": "/run/secrets/nats_auth_token",
        # AUD-191: both URLs embed the Redis password and are allowlisted for *_FILE.
        "CACHE_REDIS_URL": "/run/secrets/cache_redis_url",
        "REVOCATION_REDIS_URL": "/run/secrets/revocation_redis_url",
    },
    "notifications-worker": {
        "DATABASE_URL": "/run/secrets/notifications_database_url",
        "SECRET_KEY": "/run/secrets/secret_key",
        "NATS_AUTH_TOKEN": "/run/secrets/nats_auth_token",
    },
    "outbox-worker": {
        "DATABASE_URL": "/run/secrets/database_url",
        "SECRET_KEY": "/run/secrets/secret_key",
        "NATS_AUTH_TOKEN": "/run/secrets/nats_auth_token",
    },
    "migrations": {
        "DATABASE_URL": "/run/secrets/migration_database_url",
        "SECRET_KEY": "/run/secrets/secret_key",
    },
}


@pytest.mark.parametrize("service_name", sorted(_PRODUCTION_FILE_SECRETS))
def test_production_secret_services_do_not_inherit_plaintext_environment(
    service_name: str,
) -> None:
    base = _compose(_BASE_COMPOSE_PATH)["services"][service_name]
    production = _compose(_PRODUCTION_COMPOSE_PATH)["services"][service_name]
    assert "prod" in production.get("profiles", [])

    violations: list[str] = []
    if _merged_env_files(base, production):
        violations.append("inherited env_file can inject development credentials")

    environment = _merged_environment(base, production)
    for secret_name, expected_path in _PRODUCTION_FILE_SECRETS[service_name].items():
        plaintext_value = environment.get(secret_name)
        if plaintext_value not in (None, ""):
            violations.append(f"{secret_name} remains set beside its *_FILE input")
        if environment.get(f"{secret_name}_FILE") != expected_path:
            violations.append(f"{secret_name}_FILE does not point at {expected_path}")

    if violations:
        raise AssertionError(f"{service_name}: " + "; ".join(violations))


@pytest.mark.parametrize("service_name", ("backend", "notifications-worker"))
def test_production_spicedb_does_not_inherit_development_insecure_mode(
    service_name: str,
) -> None:
    base = _compose(_BASE_COMPOSE_PATH)["services"][service_name]
    production = _compose(_PRODUCTION_COMPOSE_PATH)["services"][service_name]
    value = _merged_environment(base, production).get("SPICEDB_INSECURE")
    assert value is None or str(value).strip().lower() in {"", "false", "0", "no"}


@pytest.mark.parametrize("service_name", ("backend", "notifications-worker"))
def test_development_compose_retains_explicit_local_environment(
    service_name: str,
) -> None:
    base = _compose(_BASE_COMPOSE_PATH)["services"][service_name]
    environment = base.get("environment") or {}

    # Positive control: local Compose intentionally keeps its development
    # environment. These assertions inspect only key names and static YAML.
    assert {"DATABASE_URL", "SECRET_KEY", "NATS_AUTH_TOKEN"} <= set(environment)
    assert environment.get("SPICEDB_INSECURE") == "true"


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("", ["base.env", "replacement.env"]),
        ("!override", ["replacement.env"]),
        ("!reset", []),
    ],
)
def test_compose_env_file_tags_preserve_merge_semantics(tmp_path, tag, expected):
    source = tmp_path / "compose.yml"
    source.write_text(f"env_file: {tag} [replacement.env]\n", encoding="utf-8")
    assert _merged_env_files({"env_file": ["base.env"]}, _compose(source)) == expected


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("", {"BASE": "kept", "NEW": "value"}),
        ("!override", {"NEW": "value"}),
        ("!reset", {}),
    ],
)
def test_compose_environment_tags_preserve_merge_semantics(tmp_path, tag, expected):
    source = tmp_path / "compose.yml"
    source.write_text(f"environment: {tag} {{NEW: value}}\n", encoding="utf-8")
    assert (
        _merged_environment({"environment": {"BASE": "kept"}}, _compose(source))
        == expected
    )


@pytest.mark.parametrize("tag", ["!unknown", "!!python/object:builtins.object"])
def test_compose_loader_rejects_unsupported_tags(tmp_path, tag):
    source = tmp_path / "compose.yml"
    source.write_text(f"environment: {tag} {{}}\n", encoding="utf-8")
    with pytest.raises(yaml.constructor.ConstructorError):
        _compose(source)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("!override 'null'", "null"),
        ("!override value", "value"),
        ("!reset ignored", None),
    ],
)
def test_compose_environment_scalar_tags(tmp_path, value, expected):
    source = tmp_path / "compose.yml"
    source.write_text(f"environment:\n  KEY: {value}\n", encoding="utf-8")
    merged = _merged_environment({"environment": {"KEY": "base"}}, _compose(source))
    assert merged == ({} if expected is None else {"KEY": expected})
