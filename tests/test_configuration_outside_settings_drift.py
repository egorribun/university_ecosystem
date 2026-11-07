"""AUD-422: inventory supported backend and service environment reads.

The variable set is derived from the code: the ``app`` package is parsed and each
``os.environ.get``, ``os.getenv`` or ``os.environ[...]`` read with a literal or
module-constant uppercase name is collected. A read without a CONFIGURATION.md
row that names a documented default fails here.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]+")
_ENV_CALLEES = frozenset({"os.getenv", "os.environ.get", "environ.get", "getenv"})
_ENV_OBJECTS = frozenset({"os.environ", "environ"})


def _literal_env_reads(source: str) -> set[str]:
    """Collect literal keys and simple module constants used as environment keys."""
    tree = ast.parse(source)
    constants: dict[str, str] = {}
    for statement in tree.body:
        targets: list[ast.expr]
        value: ast.expr | None
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets, value = [statement.target], statement.value
        else:
            continue
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                constants[target.id] = value.value

    names: set[str] = set()
    for node in ast.walk(tree):
        key: ast.expr | None = None
        if (
            isinstance(node, ast.Call)
            and node.args
            and ast.unparse(node.func) in _ENV_CALLEES
        ):
            key = node.args[0]
        elif (
            isinstance(node, ast.Subscript) and ast.unparse(node.value) in _ENV_OBJECTS
        ):
            key = node.slice
        if isinstance(key, ast.Name):
            name = constants.get(key.id)
        elif isinstance(key, ast.Constant) and isinstance(key.value, str):
            name = key.value
        else:
            name = None
        if name is not None and _ENV_NAME.fullmatch(name):
            names.add(name)
    return names


def _code_env_reads() -> dict[str, set[str]]:
    reads: dict[str, set[str]] = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        for name in _literal_env_reads(path.read_text(encoding="utf-8")):
            reads.setdefault(name, set()).add(path.relative_to(ROOT).as_posix())
    return reads


def _has_real_default(documented: dict[str, list[str]], name: str) -> bool:
    """True when some row for ``name`` states a default other than a placeholder."""
    return any(value not in ("", "-") for value in documented.get(name, []))


def _documented_defaults(document: str | None = None) -> dict[str, list[str]]:
    """Maps each CONFIGURATION.md table row name to every default cell that names it."""
    if document is None:
        document = (ROOT / "CONFIGURATION.md").read_text(encoding="utf-8")
    defaults: dict[str, list[str]] = {}
    for line in document.splitlines():
        match = re.match(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", line)
        if match is None:
            continue
        default = line.rstrip().removesuffix("|").rsplit("|", 1)[-1].strip()
        defaults.setdefault(match.group(1), []).append(default)
    return defaults


def test_every_backend_environment_read_has_a_documented_default() -> None:
    documented = _documented_defaults()
    undocumented = sorted(name for name in _code_env_reads() if name not in documented)
    without_default = sorted(
        name for name in _code_env_reads() if not _has_real_default(documented, name)
    )

    assert undocumented == []
    assert without_default == []


def test_tls_proof_diagnostics_documented_default_is_disabled() -> None:
    assert _documented_defaults()["AUD373_TLS_DIAGNOSTICS"] == ["Unset (disabled)"]


def test_literal_environment_scan_finds_known_outside_settings_reads() -> None:
    reads = _code_env_reads()

    assert {"ENABLE_PROFILING", "OTEL_SDK_DISABLED", "SPICEDB_INSECURE"} <= set(reads)
    assert len(reads) >= 10


def test_scan_detects_an_undocumented_read_in_a_snippet() -> None:
    snippet = (
        "import os\n"
        'a = os.environ.get("NEW_UNDOCUMENTED_KNOB", "x")\n'
        'b = os.getenv("ANOTHER_KNOB")\n'
        'c = os.environ["THIRD_KNOB"]\n'
        "d = os.environ.get(name_variable)\n"
        'e = os.environ.get("lowercase_name")\n'
    )

    assert _literal_env_reads(snippet) == {
        "NEW_UNDOCUMENTED_KNOB",
        "ANOTHER_KNOB",
        "THIRD_KNOB",
    }


def test_scan_detects_module_constant_environment_names() -> None:
    snippet = (
        "from typing import Final\n"
        'FIRST: Final = "CONST_ANNOTATED_KNOB"\n'
        'SECOND = "CONST_ASSIGNED_KNOB"\n'
        'UNUSED = "NOT_AN_ENVIRONMENT_READ"\n'
        'third = "LOWERCASE_IDENTIFIER"\n'
        "value = environ.get(FIRST)\n"
        "other = os.environ[SECOND]\n"
        "ignored = environ.get(third)\n"
    )

    assert _literal_env_reads(snippet) == {
        "CONST_ANNOTATED_KNOB",
        "CONST_ASSIGNED_KNOB",
    }


def test_backend_mtls_constant_names_are_discovered() -> None:
    reads = _code_env_reads()

    assert {
        "INTERNAL_HTTP_MTLS_ENABLED",
        "INTERNAL_HTTP_MTLS_SERVER_SPIFFE_ID",
        "INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS",
        "SPIFFE_ENDPOINT_SOCKET",
    } <= set(reads)


# These frontend SSR entry points use direct process.env reads or a local
# runtimeEnv alias. Build-time Vite variables and other frontend files are not
# included in this scoped check.
_FRONTEND_SSR_SOURCES = (
    "frontend/scripts/server-prod.mjs",
    "frontend/src/api/backendOrigin.ts",
    "frontend/src/server.ts",
    "frontend/src/ssrAuth.ts",
)
_FRONTEND_ENV_READ = re.compile(r"\b(?:process\.env|runtimeEnv)\.([A-Z][A-Z0-9_]*)\b")


def _frontend_ssr_env_reads(source: str) -> set[str]:
    return set(_FRONTEND_ENV_READ.findall(source))


def test_frontend_ssr_entrypoint_environment_reads_have_documented_defaults() -> None:
    reads: set[str] = set()
    for relative_path in _FRONTEND_SSR_SOURCES:
        reads.update(
            _frontend_ssr_env_reads((ROOT / relative_path).read_text(encoding="utf-8"))
        )
    document = (ROOT / "CONFIGURATION.md").read_text(encoding="utf-8")
    section = document.split("### Frontend SSR runtime\n", 1)[1].split("\n### ", 1)[0]
    documented = _documented_defaults(section)

    assert {
        "BACKEND_ORIGIN",
        "HOST",
        "PORT",
        "JWT_ISSUER",
        "NODE_ENV",
        "TSS_PRERENDERING",
    } <= reads
    assert (
        sorted(name for name in reads if not _has_real_default(documented, name)) == []
    )


def test_frontend_ssr_scan_detects_a_new_direct_read() -> None:
    snippet = "const value = process.env.NEW_RUNTIME_KNOB ?? runtimeEnv.OTHER_KNOB"

    assert _frontend_ssr_env_reads(snippet) == {"NEW_RUNTIME_KNOB", "OTHER_KNOB"}


# AUD-422: the Go services read their own environment. Names come from the literal first
# argument of the environment helpers, from the file-processor secret table, and from
# SecretFile items, so a new Go knob without a CONFIGURATION.md row fails here.
_GO_SERVICE_ROOTS = ("gateway", "ws-hub", "file-processor")
_GO_ENV_CALL = re.compile(
    r"(?:os\.Getenv|os\.LookupEnv|getEnv\w*|readSecretEnv|readSecret\w*|secretEnvOrDefault)"
    r'\(\s*"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)"'
)
_GO_ENV_FIELD = re.compile(r'\benv:\s*"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)"')
_GO_SECRET_NAME = re.compile(r'\bname\s*:=\s*"(FP_[A-Z0-9_]+)"')


def _go_env_reads(source: str) -> set[str]:
    """Environment names a Go source file reads through a literal name."""
    names: set[str] = set()
    for pattern in (_GO_ENV_CALL, _GO_ENV_FIELD, _GO_SECRET_NAME):
        names.update(pattern.findall(source))
    return names


def _go_service_reads() -> dict[str, set[str]]:
    reads: dict[str, set[str]] = {}
    for service in _GO_SERVICE_ROOTS:
        for path in sorted((ROOT / "services" / service).rglob("*.go")):
            if path.name.endswith("_test.go"):
                continue
            source = path.read_text(encoding="utf-8")
            for name in _go_env_reads(source):
                reads.setdefault(name, set()).add(path.relative_to(ROOT).as_posix())
    return reads


def test_every_go_service_environment_read_has_a_documented_default() -> None:
    documented = _documented_defaults()
    reads = _go_service_reads()

    undocumented = sorted(name for name in reads if name not in documented)
    without_default = sorted(
        name for name in reads if not _has_real_default(documented, name)
    )

    assert undocumented == []
    assert without_default == []


def test_go_environment_scan_finds_known_service_reads() -> None:
    reads = _go_service_reads()

    assert {"GATEWAY_PORT", "WS_HUB_PORT", "FP_JWT_SECRET", "NATS_STREAM_CHAT"} <= set(
        reads
    )
    assert len(reads) >= 60


def test_go_scan_detects_an_undocumented_read_in_a_snippet() -> None:
    snippet = (
        "package config\n"
        'port := getEnvInt("NEW_GATEWAY_KNOB", 1)\n'
        'raw := os.Getenv("ANOTHER_KNOB")\n'
        'v, ok := os.LookupEnv("LOOKED_UP_KNOB")\n'
        'secret, _, err := readSecretEnv("READ_SECRET_KNOB")\n'
        'fallback, err := secretEnvOrDefault("SECRET_DEFAULT_KNOB", "fallback")\n'
        '{key: "x", env: "SECRET_FIELD_KNOB"}\n'
        'name := "FP_NAMED_KNOB"\n'
        'kind := getEnv("lower_case", "x")\n'
        'shape := getEnv("PLAIN", "x")\n'
    )

    assert _go_env_reads(snippet) == {
        "NEW_GATEWAY_KNOB",
        "ANOTHER_KNOB",
        "LOOKED_UP_KNOB",
        "READ_SECRET_KNOB",
        "SECRET_DEFAULT_KNOB",
        "SECRET_FIELD_KNOB",
        "FP_NAMED_KNOB",
    }


def test_file_processor_viper_settings_have_documented_defaults() -> None:
    source = (ROOT / "services/file-processor/internal/config/config.go").read_text(
        encoding="utf-8"
    )
    assert 'viper.SetEnvPrefix("FP")' in source
    assert "viper.AutomaticEnv()" in source
    config = re.search(r"(?ms)^type Config struct \{(.*?)^\}", source)
    assert config is not None
    fields = re.findall(r'mapstructure:"([a-z][a-z0-9_]*)"', config.group(1))
    assert len(fields) >= 30
    names = {f"FP_{field.upper()}" for field in fields}
    documented = _documented_defaults()

    assert sorted(name for name in names if name not in documented) == []
    assert (
        sorted(name for name in names if not _has_real_default(documented, name)) == []
    )


def test_file_processor_literal_defaults_match_reference() -> None:
    source = (ROOT / "services/file-processor/internal/config/config.go").read_text(
        encoding="utf-8"
    )
    defaults = re.findall(
        r'viper\.SetDefault\("([a-z][a-z0-9_]*)",\s*("(?:[^"\\]|\\.)*"|true|false|\d+)\)',
        source,
    )
    assert len(defaults) >= 20
    documented = _documented_defaults()
    for key, value in defaults:
        # The reference points operators to the source for bundled credentials;
        # don't copy credential-shaped defaults into assertion output.
        if key in {"minio_access_key", "minio_secret_key"}:
            continue
        cell = documented[f"FP_{key.upper()}"][0]
        if value.startswith('"'):
            expected = json.loads(value)
            if expected:
                assert f"`{expected}`" in cell
            else:
                assert "Unset" in cell or "Empty" in cell
        else:
            assert f"`{value}`" in cell
