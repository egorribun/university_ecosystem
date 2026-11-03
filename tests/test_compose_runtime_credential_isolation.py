"""Runtime credential isolation contract for the Docker Compose stacks (ADR-047).

A runtime container may receive only the database credential of its own role.
The bootstrap superuser password, the migrator and the other roles' passwords and
the URLs that embed them must never reach a runtime container through env_file or
environment. Runtime services take a names-only allowlist (or the launcher-redacted
workers file) as env_file; the values are resolved from the interpolation env files,
so this module resolves every env_file entry against the example env files and the
launcher redaction, then checks each service definition in each compose file.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.full.yml",
    "docker-compose.prod.yml",
)
APP_ALLOWLIST = "docker-compose.runtime-app.allowlist"
WORKER_ALLOWLIST = "docker-compose.runtime-worker.allowlist"

_SOURCE_FILES = {
    path.name: path
    for path in (
        ROOT / "docker-compose.yml",
        ROOT / "docker-compose.full.yml",
        ROOT / "docker-compose.prod.yml",
        ROOT / "docker-compose.runtime-app.allowlist",
        ROOT / "docker-compose.runtime-worker.allowlist",
        ROOT / ".env.example",
        ROOT / ".env.docker.example",
        ROOT / "start-docker.ps1",
    )
}

# Names whose values are database superuser or role credentials, or URLs embedding them.
SUPERUSER_KEYS = frozenset(
    {"POSTGRES_PASSWORD", "PGPASSWORD", "SQL_PASSWORD", "POSTGRES_PWD"}
)
ROLE_PASSWORD_KEYS = frozenset(
    {"UE_MIGRATOR_DB_PASSWORD", "UE_APP_DB_PASSWORD", "UE_WORKER_DB_PASSWORD"}
)
ROLE_URL_KEYS = frozenset(
    {"DATABASE_URL_SYNC", "MIGRATION_DATABASE_URL", "NOTIFICATIONS_DATABASE_URL"}
)
CREDENTIAL_VARS = SUPERUSER_KEYS | ROLE_PASSWORD_KEYS | ROLE_URL_KEYS | {"DATABASE_URL"}

# Settings that must never be injected into a runtime container's allowlist.
APP_EXCLUDED = frozenset(
    {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "UE_MIGRATOR_DB_PASSWORD",
        "UE_APP_DB_PASSWORD",
        "UE_WORKER_DB_PASSWORD",
        "DATABASE_URL",
        "DATABASE_URL_SYNC",
        "NOTIFICATIONS_DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "REVOCATION_REDIS_PASSWORD",
        "REVOCATION_REDIS_URL",
    }
)
WORKER_EXCLUDED = APP_EXCLUDED | frozenset(
    {
        "MFA_EMAIL_OTP_HMAC_KEYS",
        "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID",
        "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID",
    }
)

# Services that bootstrap or migrate the database; they may name superuser or role secrets.
BOOTSTRAP_ALLOWED_REFS: dict[str, frozenset[str]] = {
    "postgres": frozenset({"POSTGRES_PASSWORD"}),
    "postgres-databases-init": frozenset({"POSTGRES_PASSWORD"}),
    "postgres-roles-init": frozenset({"POSTGRES_PASSWORD"}) | ROLE_PASSWORD_KEYS,
    "spicedb-migrate": frozenset({"POSTGRES_PASSWORD"}),
    "temporal-admin-tools": frozenset({"POSTGRES_PASSWORD"}),
}

# Runtime services still given the superuser password because they have no dedicated
# database role yet (the infrastructure/postgres-roles bootstrap owns role creation).
# The exact set is pinned by test_superuser_runtime_exceptions_are_exact; removing an
# entry requires provisioning its role and wiring a role-scoped DATABASE URL first.
KNOWN_SUPERUSER_RUNTIME: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "spicedb": (frozenset({"POSTGRES_PASSWORD"}), frozenset({"PGPASSWORD"})),
    "temporal": (frozenset({"POSTGRES_PASSWORD"}), frozenset({"POSTGRES_PWD"})),
}

# Each runtime service may reference only the credential of its own role.
OWNER_REFS: dict[str, frozenset[str]] = {
    "backend": frozenset({"DATABASE_URL", "UE_APP_DB_PASSWORD"}),
    "outbox-worker": frozenset({"DATABASE_URL", "UE_APP_DB_PASSWORD"}),
    "notifications-worker": frozenset(
        {"NOTIFICATIONS_DATABASE_URL", "UE_WORKER_DB_PASSWORD"}
    ),
    "migrations": frozenset({"MIGRATION_DATABASE_URL", "UE_MIGRATOR_DB_PASSWORD"}),
}

_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=")
_INTERPOLATION = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")


def _read(name: str) -> str:
    return _SOURCE_FILES[name].read_text(encoding="utf-8")


def _load_compose(name: str) -> dict[str, Any]:
    # Compose's !reset and !override tags only mark merge behaviour; the values are
    # plain YAML for this contract, so strip the tags before the safe load.
    source = _read(name).replace("!override", "").replace("!reset", "")
    document: dict[str, Any] = yaml.safe_load(source)
    return document


def _example_keys(name: str) -> set[str]:
    return {
        match.group(1)
        for line in _read(name).splitlines()
        if (match := _KEY_LINE.match(line))
    }


def _allowlist_names(name: str) -> set[str]:
    return {
        line.strip()
        for line in _read(name).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _launcher_env_keys() -> set[str]:
    script = _read("start-docker.ps1").replace("\r\n", "\n")
    keys: set[str] = set()
    for block in re.findall(
        r'\$(?:dockerEnv|composeEnv) = @"\n(.*?)\n"@', script, re.S
    ):
        keys.update(
            match.group(1)
            for line in block.splitlines()
            if (match := _KEY_LINE.match(line))
        )
    return keys


def _launcher_worker_redaction() -> re.Pattern[str]:
    """Return the regex that start-docker.ps1 uses to redact .env.docker.workers."""
    script = _read("start-docker.ps1").replace("\r\n", "\n")
    block = re.search(r"\$redactedPattern = \((.*?)\n    \)", script, re.S)
    assert block is not None, "start-docker.ps1 no longer defines $redactedPattern"
    return re.compile("".join(re.findall(r"'([^']*)'", block.group(1))))


def _union_example_names() -> set[str]:
    return (
        _example_keys(".env.example")
        | _example_keys(".env.docker.example")
        | _launcher_env_keys()
    )


def _env_file_names(entry: str) -> set[str]:
    if entry == ".env":
        return _example_keys(".env.example")
    if entry == ".env.docker":
        return _example_keys(".env.docker.example")
    if entry == ".env.docker.workers":
        redacted = _launcher_worker_redaction()
        return {
            key
            for key in _example_keys(".env.docker.example")
            if not redacted.match(f"{key}=")
        }
    if entry in (APP_ALLOWLIST, WORKER_ALLOWLIST):
        return _allowlist_names(entry)
    raise AssertionError(f"env_file {entry!r} has no resolution rule in this contract")


def _env_file_entries(service: dict[str, Any]) -> list[str]:
    entries = service.get("env_file") or []
    return [entry["path"] if isinstance(entry, dict) else entry for entry in entries]


def _service_env_names(service: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for entry in _env_file_entries(service):
        names |= _env_file_names(entry)
    environment = service.get("environment") or {}
    if isinstance(environment, list):
        names |= {item.split("=", 1)[0] for item in environment}
    else:
        names |= set(environment)
    return names


def _referenced_variables(service: dict[str, Any]) -> set[str]:
    return set(_INTERPOLATION.findall(yaml.safe_dump(service)))


def _credential_violations(file_name: str, document: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for name, service in document.get("services", {}).items():
        refs = _referenced_variables(service) & CREDENTIAL_VARS
        names = _service_env_names(service)
        if name in BOOTSTRAP_ALLOWED_REFS:
            if refs - BOOTSTRAP_ALLOWED_REFS[name]:
                violations.append(
                    f"{file_name}:{name} references {sorted(refs - BOOTSTRAP_ALLOWED_REFS[name])}"
                )
            continue
        if name in KNOWN_SUPERUSER_RUNTIME:
            allowed_refs, allowed_keys = KNOWN_SUPERUSER_RUNTIME[name]
            if refs - allowed_refs or (names & SUPERUSER_KEYS) - allowed_keys:
                violations.append(
                    f"{file_name}:{name} exposes more than its superuser login"
                )
            continue
        owner = OWNER_REFS.get(name, frozenset())
        if refs - owner:
            violations.append(
                f"{file_name}:{name} references foreign credentials {sorted(refs - owner)}"
            )
        leaked_keys = (
            names & (SUPERUSER_KEYS | ROLE_PASSWORD_KEYS | ROLE_URL_KEYS)
        ) - owner
        if leaked_keys:
            violations.append(f"{file_name}:{name} receives {sorted(leaked_keys)}")
    return violations


def _superuser_runtime_services(document: dict[str, Any]) -> set[str]:
    return {
        name
        for name, service in document.get("services", {}).items()
        if name not in BOOTSTRAP_ALLOWED_REFS
        and (
            _referenced_variables(service) & SUPERUSER_KEYS
            or _service_env_names(service) & SUPERUSER_KEYS
        )
    }


def test_runtime_services_receive_no_superuser_or_foreign_role_credentials() -> None:
    for file_name in COMPOSE_FILES:
        assert _credential_violations(file_name, _load_compose(file_name)) == []


def test_superuser_runtime_exceptions_are_exact() -> None:
    """Only the documented runtime services may still hold the superuser password."""
    for file_name in ("docker-compose.yml", "docker-compose.full.yml"):
        assert _superuser_runtime_services(_load_compose(file_name)) == set(
            KNOWN_SUPERUSER_RUNTIME
        ), file_name


def test_runtime_services_use_role_scoped_env_files() -> None:
    for file_name in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _load_compose(file_name)["services"]
        assert _env_file_entries(services["backend"]) == [APP_ALLOWLIST]
        assert _env_file_entries(services["migrations"]) == [APP_ALLOWLIST]
    base = _load_compose("docker-compose.yml")["services"]
    for worker in ("notifications-worker", "outbox-worker"):
        assert _env_file_entries(base[worker]) == [WORKER_ALLOWLIST]
    full = _load_compose("docker-compose.full.yml")["services"]
    for worker in ("notifications-worker", "outbox-worker"):
        assert _env_file_entries(full[worker]) == [".env.docker.workers"]


def test_prod_overlay_resets_inherited_env_files() -> None:
    services = _load_compose("docker-compose.prod.yml")["services"]
    for name in ("backend", "notifications-worker", "outbox-worker", "migrations"):
        assert services[name]["env_file"] == []


def test_allowlists_equal_examples_and_launcher_minus_exclusions() -> None:
    union = _union_example_names()
    expected_app = union - APP_EXCLUDED
    expected_worker = union - WORKER_EXCLUDED
    assert _allowlist_names(APP_ALLOWLIST) == expected_app
    assert _allowlist_names(WORKER_ALLOWLIST) == expected_worker
    assert not _allowlist_names(APP_ALLOWLIST) & APP_EXCLUDED
    assert not _allowlist_names(WORKER_ALLOWLIST) & WORKER_EXCLUDED


def test_launcher_worker_redaction_covers_worker_exclusions() -> None:
    redacted = _launcher_worker_redaction()
    for key in sorted(WORKER_EXCLUDED & _example_keys(".env.docker.example")):
        assert redacted.match(f"{key}="), (
            f"{key} must be redacted from .env.docker.workers"
        )


def test_negative_control_detects_whole_env_file_injection() -> None:
    """The checker must flag the former whole-file wiring that leaked credentials."""
    document = copy.deepcopy(_load_compose("docker-compose.full.yml"))
    document["services"]["backend"]["env_file"] = [".env.docker"]
    document["services"]["notifications-worker"]["environment"][
        "UE_APP_DB_PASSWORD"
    ] = "${UE_APP_DB_PASSWORD}"
    violations = _credential_violations("synthetic", document)
    assert any(v.startswith("synthetic:backend receives") for v in violations)
    assert any(v.startswith("synthetic:notifications-worker") for v in violations)
