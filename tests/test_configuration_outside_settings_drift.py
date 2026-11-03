"""AUD-422: every backend environment read outside ``Settings`` is documented.

The variable set is derived from the code: the ``app`` package is parsed and each
literal ``os.environ.get``, ``os.getenv`` or ``os.environ[...]`` read with an
uppercase name is collected. A read without a CONFIGURATION.md row that names a
documented default fails here, so a new knob cannot ship undocumented.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]+")
_ENV_CALLEES = frozenset({"os.getenv", "os.environ.get", "environ.get", "getenv"})
_ENV_OBJECTS = frozenset({"os.environ", "environ"})


def _literal_env_reads(source: str) -> set[str]:
    """Uppercase names read from the process environment with a literal key."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
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
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if _ENV_NAME.fullmatch(key.value):
                names.add(key.value)
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


def _documented_defaults() -> dict[str, list[str]]:
    """Maps each CONFIGURATION.md table row name to every default cell that names it."""
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


# AUD-422: the Go services read their own environment. Names come from the literal first
# argument of the environment helpers, from the file-processor secret table, and from
# SecretFile items, so a new Go knob without a CONFIGURATION.md row fails here.
_GO_SERVICE_ROOTS = ("gateway", "ws-hub", "file-processor")
_GO_ENV_CALL = re.compile(
    r"(?:os\.Getenv|os\.LookupEnv|getEnv\w*|readSecretEnv|readSecret\w*)"
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
        "SECRET_FIELD_KNOB",
        "FP_NAMED_KNOB",
    }
