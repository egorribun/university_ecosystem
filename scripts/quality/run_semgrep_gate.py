#!/usr/bin/env python3
"""Run the pinned, disposition-gated Semgrep scan used by CI and pre-commit."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import unicodedata
import urllib.parse
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RULES_REPOSITORY = "semgrep/semgrep-rules"
RULES_URL = "https://github.com/semgrep/semgrep-rules.git"
CONTAINER_TMP = PurePosixPath("/", "tmp").as_posix()
IMAGE_PATTERN = re.compile(
    r"semgrep/semgrep:[0-9]+\.[0-9]+\.[0-9]+@sha256:[0-9a-f]{64}\Z"
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
GIT_TIMEOUT_SECONDS = 300
SCAN_TIMEOUT_SECONDS = 900
HELM_ARCHIVE_MAX_BYTES = 128 * 1024 * 1024
HELM_ARCHIVE_TIMEOUT_SECONDS = 30
HELM_ARCHIVE_CHUNK_BYTES = 64 * 1024
HELM_ARCHIVE_HOST = "get.helm.sh"
HELM_ARCHIVE_MAX_REDIRECTS = 3
HELM_TEMPLATE_ROOTS = (
    "charts/redis-compat/templates",
    "charts/revocation-store/templates",
    "charts/university-ecosystem/templates",
)
HELM_PROFILE_NAMES = frozenset(
    {
        "university-development",
        "university-staging",
        "university-production",
        "university-feature-enabled-development",
        "revocation-store-development",
        "revocation-store-staging",
        "revocation-store-production",
        "gateway-api-isolated-synthetic-apis",
    }
)
HELM_GUARD_ONLY_PATHS = frozenset(
    {
        "charts/university-ecosystem/templates/validate-config.yaml",
        "charts/university-ecosystem/templates/deployment-contract.yaml",
        "charts/revocation-store/templates/validate-config.yaml",
        "charts/revocation-store/templates/deployment-contract.yaml",
    }
)
REVIEWED_UNIGNORED_MTS_TARGETS = frozenset(
    {
        "frontend/scripts/contentTypes.d.mts",
        "frontend/scripts/live-e2e-credentials.d.mts",
        "frontend/scripts/live-e2e-output-dir.d.mts",
        "frontend/scripts/live-registration-admission.d.mts",
        "frontend/scripts/server-csp.d.mts",
        "frontend/scripts/wasm-fuzzer.d.mts",
        "frontend/vite.config.mts",
    }
)
MTS_RULE_LANGUAGE_ALIASES = frozenset({"javascript", "js", "typescript", "ts"})
REVIEWED_UNIGNORED_DOCKERFILE_TARGETS = frozenset(
    {
        "Dockerfile.protogen",
        "Dockerfile.test",
        "containers/quality/Dockerfile.performance-rust",
        "infrastructure/observability/alloy/Dockerfile.docker-log-proxy",
    }
)
DOCKERFILE_RULE_ID = "dockerfile.security.php-version-usage.php-version-usage"
DOCKERFILE_SCAN_TIMEOUT_SECONDS = 60
INLINE_JAVASCRIPT_SCAN_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class InlineJavaScriptSource:
    """Per-run source and slice identity derived from one stage-zero HTML blob."""

    path: str
    mode: str
    oid: str
    source_sha256: str
    byte_start: int
    byte_end: int
    source_char_start: int
    source_char_end: int
    source_start_line: int
    source_start_column: int
    source_end_line: int
    view_sha256: str
    view_byte_length: int
    view_char_length: int
    view_line_count: int
    view_line_start_offsets: tuple[int, ...]
    view_line_byte_lengths: tuple[int, ...]
    external_sources: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class InlineJavaScriptSlice:
    """Current inline JavaScript body extracted from its immutable HTML bytes."""

    view: bytes
    byte_start: int
    byte_end: int
    char_start: int
    char_end: int
    source_start_line: int
    source_start_column: int
    source_end_line: int
    external_sources: tuple[str, ...]


REVIEWED_INLINE_JAVASCRIPT_PATHS = (
    "frontend/index.html",
    "frontend/public/offline.html",
)
INLINE_JAVASCRIPT_ALIASES = tuple(
    f"target-{index:02d}/inline.js"
    for index in range(len(REVIEWED_INLINE_JAVASCRIPT_PATHS))
)
INLINE_JAVASCRIPT_RULE_LANGUAGES = frozenset({"javascript", "js"})
_SUPPORTED_INLINE_JAVASCRIPT_TYPES = frozenset(
    {"", "module", "application/javascript", "text/javascript"}
)

WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
    *(f"COM{number}" for number in "¹²³"),
    *(f"LPT{number}" for number in "¹²³"),
}

CommandRunner = Callable[..., subprocess.CompletedProcess[Any]]


@dataclass(frozen=True)
class IndexEntry:
    """One regular stage-zero entry from the Git index."""

    path: PurePosixPath
    mode: str
    oid: str
    stage: int

    def identity(self) -> tuple[str, str, str, int]:
        return self.path.as_posix(), self.mode, self.oid, self.stage


@dataclass(frozen=True)
class InlineJavaScriptBinding:
    """Mapped position data for a parser-safe JavaScript source alias."""

    alias: str
    path: str
    source_mode: str
    source_oid: str
    source_sha256: str
    source_start_line: int
    source_start_column: int
    source_byte_start: int
    source_byte_end: int
    source_char_start: int
    source_char_end: int
    source_end_line: int
    view_byte_length: int
    view_char_length: int
    view_line_count: int
    view_line_start_offsets: tuple[int, ...]
    view_line_byte_lengths: tuple[int, ...]
    external_sources: tuple[tuple[str, str], ...]
    view_sha256: str


class SemgrepGateError(RuntimeError):
    """Raised when the pinned Semgrep scan cannot produce trustworthy evidence."""


def _windows_path_key(path: PurePosixPath) -> tuple[str, ...]:
    key: list[str] = []
    for component in path.parts:
        if (
            any(character in component for character in '<>:"|?*')
            or any(ord(character) < 32 for character in component)
            or component.endswith((".", " "))
        ):
            raise SemgrepGateError(
                f"staged Semgrep target is not portable to Windows: {path.as_posix()}"
            )
        normalized = unicodedata.normalize("NFC", component).casefold()
        device_base = normalized.split(".", 1)[0].upper()
        if device_base in WINDOWS_DEVICE_NAMES:
            raise SemgrepGateError(
                f"staged Semgrep target uses a reserved Windows name: {path.as_posix()}"
            )
        key.append(normalized)
    return tuple(key)


def _validate_windows_path_collisions(entries: Sequence[IndexEntry]) -> None:
    by_key: dict[tuple[str, ...], str] = {}
    keys: list[tuple[str, ...]] = []
    for entry in entries:
        path_text = entry.path.as_posix()
        key = _windows_path_key(entry.path)
        existing = by_key.get(key)
        if existing is not None and existing != path_text:
            raise SemgrepGateError(
                "staged Semgrep targets collide on Windows: "
                f"{existing!r} and {path_text!r}"
            )
        by_key[key] = path_text
        keys.append(key)
    for key in keys:
        for length in range(1, len(key)):
            parent_key = key[:length]
            if parent_key in by_key:
                raise SemgrepGateError(
                    "staged Semgrep targets conflict as Windows file and directory paths: "
                    f"{by_key[parent_key]!r} and {by_key[key]!r}"
                )


def _validate_semgrep_ignore_policy(
    repository_root: Path,
) -> Callable[[str], bool] | None:
    gate_path = repository_root / "scripts" / "quality" / "semgrep_dispositions_gate.py"
    module_name = "_ue_semgrep_dispositions_gate_policy"
    try:
        specification = importlib.util.spec_from_file_location(module_name, gate_path)
        if specification is None or specification.loader is None:
            raise ImportError("cannot load the Semgrep dispositions gate")
        module = importlib.util.module_from_spec(specification)
        sys.modules[module_name] = module
        previous_dont_write_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            specification.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous_dont_write_bytecode
        gate_error = module.GateError
        validator = module.validate_semgrep_ignore_policy
        ignore_matcher = getattr(module, "_matches_reviewed_semgrep_ignore", None)
    except (ImportError, OSError, SyntaxError, AttributeError) as exc:
        raise SemgrepGateError("Semgrep ignore validator is unavailable") from exc
    finally:
        sys.modules.pop(module_name, None)
    try:
        validator(repository_root)
    except gate_error as exc:
        raise SemgrepGateError(f"Semgrep ignore policy rejected: {exc}") from exc
    return ignore_matcher if callable(ignore_matcher) else None


def _mts_scan_targets(
    scan_root: Path,
    overlay_target_hashes: dict[str, str],
    ignore_matcher: Callable[[str], bool] | None,
) -> tuple[str, ...]:
    """Return only reviewed, unignored MTS targets from the validated overlay."""

    candidates = sorted(
        relative
        for relative in overlay_target_hashes
        if PurePosixPath(relative).suffix.lower() == ".mts"
    )
    if not candidates:
        return ()
    if ignore_matcher is None:
        raise SemgrepGateError(
            "reviewed Semgrep ignore matcher is required for MTS target selection"
        )

    targets: list[str] = []
    for relative in candidates:
        if ignore_matcher(relative):
            continue
        if relative not in REVIEWED_UNIGNORED_MTS_TARGETS:
            raise SemgrepGateError(
                f"unreviewed unignored MTS target requires policy review: {relative}"
            )
        target = scan_root.joinpath(*PurePosixPath(relative).parts)
        if target.is_symlink() or target.is_junction() or not target.is_file():
            raise SemgrepGateError(
                f"MTS target is missing, linked or non-regular: {relative}"
            )
        targets.append(relative)
    return tuple(targets)


def _write_mts_rules_config(
    selected_config_path: Path, destination: Path
) -> tuple[str, tuple[str, ...]]:
    """Write selected JavaScript/TypeScript rules for explicit MTS targets."""

    typescript_rules = _selected_mts_rules(selected_config_path)
    if destination.is_symlink() or destination.is_junction() or destination.exists():
        raise SemgrepGateError("MTS Semgrep config destination is not fresh")
    payload = _serialize_rule_config(typescript_rules)
    try:
        destination.write_bytes(payload)
    except OSError as exc:
        raise SemgrepGateError(f"cannot write MTS Semgrep config: {exc}") from exc
    return hashlib.sha256(payload).hexdigest(), tuple(
        rule["id"] for rule in typescript_rules
    )


def _serialize_rule_config(rules: Sequence[dict[str, Any]]) -> bytes:
    return (
        json.dumps(
            {"rules": list(rules)},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _selected_mts_rules(selected_config_path: Path) -> list[dict[str, Any]]:
    """Load selected JS/TS rules and reject path filters the aliases cannot preserve."""

    if selected_config_path.is_symlink() or selected_config_path.is_junction():
        raise SemgrepGateError("selected Semgrep config may not be linked")
    try:
        if not selected_config_path.is_file():
            raise SemgrepGateError("selected Semgrep config is missing")
        source = json.loads(selected_config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemgrepGateError(f"cannot read selected Semgrep config: {exc}") from exc
    if not isinstance(source, dict) or set(source) != {"rules"}:
        raise SemgrepGateError("selected Semgrep config has an unsupported shape")
    rules = source.get("rules")
    if not isinstance(rules, list):
        raise SemgrepGateError("selected Semgrep config has no rule list")
    typescript_rules: list[dict[str, Any]] = []
    rule_ids: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise SemgrepGateError("selected Semgrep config contains a malformed rule")
        rule_id = rule.get("id")
        languages = rule.get("languages")
        if (
            not isinstance(rule_id, str)
            or not rule_id
            or rule_id in rule_ids
            or not isinstance(languages, list)
            or any(not isinstance(language, str) for language in languages)
        ):
            raise SemgrepGateError(
                "selected Semgrep config contains an invalid rule identity"
            )
        rule_ids.add(rule_id)
        if MTS_RULE_LANGUAGE_ALIASES.intersection(languages):
            if rule.get("paths") is not None:
                raise SemgrepGateError(
                    "JavaScript/TypeScript supplemental scan cannot preserve a rule path filter"
                )
            typescript_rules.append(rule)
    if not typescript_rules:
        raise SemgrepGateError(
            "selected Semgrep config has no JavaScript/TypeScript rules"
        )
    return typescript_rules


def _ensure_mts_rules_config(
    selected_config_path: Path, destination: Path
) -> tuple[str, tuple[str, ...]]:
    """Reuse an identical MTS config or create one for the inline-JS scan."""

    rules = _selected_mts_rules(selected_config_path)
    payload = _serialize_rule_config(rules)
    if destination.is_symlink() or destination.is_junction():
        raise SemgrepGateError("MTS Semgrep config is linked")
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != payload:
            raise SemgrepGateError("existing MTS Semgrep config changed")
    else:
        try:
            destination.write_bytes(payload)
        except OSError as exc:
            raise SemgrepGateError(f"cannot write MTS Semgrep config: {exc}") from exc
    return hashlib.sha256(payload).hexdigest(), tuple(rule["id"] for rule in rules)


def _javascript_rule_ids(config_path: Path) -> tuple[str, ...]:
    rules = _selected_mts_rules(config_path)
    result = tuple(
        rule["id"]
        for rule in rules
        if INLINE_JAVASCRIPT_RULE_LANGUAGES.intersection(rule["languages"])
    )
    if not result:
        raise SemgrepGateError("selected config has no JavaScript rules")
    return result


class _InlineScriptParser(HTMLParser):
    """Locate executable inline script bodies without reparsing the HTML by regex."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.line_starts = [0]
        self.line_starts.extend(
            index + 1 for index, character in enumerate(source) if character == "\n"
        )
        self.open_script: tuple[int, str, str | None] | None = None
        self.inline_scripts: list[tuple[int, int, str]] = []
        self.external_scripts: list[str] = []
        self.errors: list[str] = []

    def _char_offset(self, position: tuple[int, int]) -> int:
        line, column = position
        if line < 1 or line > len(self.line_starts):
            raise SemgrepGateError("HTML parser returned an invalid source position")
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        if self.open_script is not None:
            self.errors.append("nested script start tag")
            return
        attributes: dict[str, str | None] = {}
        for name, value in attrs:
            key = name.lower()
            if key in attributes:
                self.errors.append("duplicate script attribute")
                return
            attributes[key] = value
        script_type = (attributes.get("type") or "").strip().lower()
        if script_type not in _SUPPORTED_INLINE_JAVASCRIPT_TYPES:
            self.errors.append("unsupported inline script type")
            return
        start = self._char_offset(self.getpos()) + len(self.get_starttag_text() or "")
        if "src" in attributes:
            source = attributes["src"]
            if (
                not isinstance(source, str)
                or not source
                or source != source.strip()
                or any(ord(character) < 32 for character in source)
            ):
                self.errors.append("external script has an empty src attribute")
                return
            self.open_script = (start, "external", source)
            return
        self.open_script = (start, "inline", None)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script":
            return
        if self.open_script is None:
            self.errors.append("script closing tag without an open script")
            return
        start, kind, external_source = self.open_script
        end = self._char_offset(self.getpos())
        self.open_script = None
        if kind == "inline":
            if end < start:
                self.errors.append("script body has negative length")
            else:
                self.inline_scripts.append((start, end, self.source[start:end]))
        elif self.source[start:end].strip():
            self.errors.append("external script also contains inline code")
        elif external_source is not None:
            self.external_scripts.append(external_source)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self.errors.append("self-closing script tags are unsupported")


def _extract_reviewed_inline_script(
    source_bytes: bytes, path: str
) -> InlineJavaScriptSlice:
    try:
        text = source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SemgrepGateError(
            f"inline JavaScript source is not UTF-8: {path}"
        ) from exc
    parser = _InlineScriptParser(text)
    try:
        parser.feed(text)
        parser.close()
    except (AssertionError, ValueError) as exc:
        raise SemgrepGateError(
            f"inline JavaScript HTML parsing failed: {path}"
        ) from exc
    if (
        parser.errors
        or parser.open_script is not None
        or len(parser.inline_scripts) != 1
    ):
        raise SemgrepGateError(
            f"inline JavaScript source has missing or ambiguous script blocks: {path}"
        )
    char_start, char_end, body = parser.inline_scripts[0]
    prefix = text[:char_start]
    body_bytes = body.encode("utf-8")
    byte_start = len(prefix.encode("utf-8"))
    byte_end = byte_start + len(body_bytes)
    start_line = prefix.count("\n") + 1
    start_column = len(prefix.rsplit("\n", 1)[-1]) + 1
    end_line = text[:char_end].count("\n") + 1
    try:
        prefix.rsplit("\n", 1)[-1].encode("ascii", errors="strict")
        _inline_view_line_geometry(body_bytes)
    except (UnicodeEncodeError, SemgrepGateError) as exc:
        raise SemgrepGateError(
            f"inline JavaScript source slice has unsupported column encoding: {path}"
        ) from exc
    return InlineJavaScriptSlice(
        view=body_bytes,
        byte_start=byte_start,
        byte_end=byte_end,
        char_start=char_start,
        char_end=char_end,
        source_start_line=start_line,
        source_start_column=start_column,
        source_end_line=end_line,
        external_sources=tuple(parser.external_scripts),
    )


_INLINE_EXTERNAL_SCRIPT_SUFFIXES = frozenset(
    {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
)


def _resolve_inline_external_sources(
    html_path: str, sources: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    resolved: list[tuple[str, str]] = []
    for source in sources:
        if not isinstance(source, str) or not source:
            raise SemgrepGateError("external script src is malformed")
        parsed = urllib.parse.urlsplit(source)
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or not parsed.path
            or "\\" in parsed.path
        ):
            raise SemgrepGateError(
                "external script src must resolve to a local frontend source"
            )
        try:
            url_path = urllib.parse.unquote(parsed.path, errors="strict")
        except UnicodeDecodeError as exc:
            raise SemgrepGateError("external script src is not valid UTF-8") from exc
        if "\\" in url_path or url_path.startswith("//"):
            raise SemgrepGateError(
                "external script src must resolve to a local frontend source"
            )
        parts = (
            ["frontend"]
            if url_path.startswith("/")
            else list(PurePosixPath(html_path).parent.parts)
        )
        for component in url_path.split("/"):
            if component in {"", "."}:
                continue
            if component == "..":
                if len(parts) <= 1:
                    raise SemgrepGateError(
                        "external script src escapes the frontend snapshot"
                    )
                parts.pop()
                continue
            if any(ord(character) < 32 for character in component) or any(
                character in component for character in '<>:"|?*'
            ):
                raise SemgrepGateError("external script src path is not portable")
            parts.append(component)
        resolved_path = PurePosixPath(*parts).as_posix()
        if (
            not resolved_path.startswith("frontend/")
            or PurePosixPath(resolved_path).suffix.lower()
            not in _INLINE_EXTERNAL_SCRIPT_SUFFIXES
        ):
            raise SemgrepGateError(
                "external script src must resolve to a local JavaScript or TypeScript file"
            )
        resolved.append((source, resolved_path))
    return tuple(resolved)


def _inline_view_line_geometry(view: bytes) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return byte offsets and lengths for the exact ASCII-pinned parser view."""

    try:
        view.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise SemgrepGateError(
            "reviewed inline JavaScript views must remain ASCII for source mapping"
        ) from exc
    starts = [0]
    for offset, byte in enumerate(view):
        if byte == 0x0A:
            starts.append(offset + 1)
    lengths: list[int] = []
    for index, start in enumerate(starts):
        line_end = starts[index + 1] - 1 if index + 1 < len(starts) else len(view)
        lengths.append(line_end - start)
    return tuple(starts), tuple(lengths)


def _snapshot_manifest_bytes(manifest: Sequence[dict[str, str]]) -> bytes:
    return (
        json.dumps(
            {"targets": manifest},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _stage_zero_blob_oid(content: bytes, expected_oid: str) -> str:
    if not isinstance(expected_oid, str) or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", expected_oid
    ):
        raise SemgrepGateError("inline JavaScript source has malformed stage-zero OID")
    header = b"blob " + str(len(content)).encode("ascii") + b"\0"
    algorithm = "sha1" if len(expected_oid) == 40 else "sha256"
    return hashlib.new(algorithm, header + content, usedforsecurity=False).hexdigest()


def _derive_inline_javascript_source(
    path: str, entry: dict[str, str], content: bytes
) -> InlineJavaScriptSource:
    if (
        entry.get("path") != path
        or entry.get("stage") != "0"
        or entry.get("mode") not in {"100644", "100755"}
        or not isinstance(entry.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        or _stage_zero_blob_oid(content, entry.get("oid", "")) != entry.get("oid")
        or hashlib.sha256(content).hexdigest() != entry["sha256"]
    ):
        raise SemgrepGateError(
            f"inline JavaScript source lacks exact stage-zero identity: {path}"
        )
    source_slice = _extract_reviewed_inline_script(content, path)
    line_starts, line_lengths = _inline_view_line_geometry(source_slice.view)
    external_sources = _resolve_inline_external_sources(
        path, source_slice.external_sources
    )
    return InlineJavaScriptSource(
        path=path,
        mode=entry["mode"],
        oid=entry["oid"],
        source_sha256=entry["sha256"],
        byte_start=source_slice.byte_start,
        byte_end=source_slice.byte_end,
        source_char_start=source_slice.char_start,
        source_char_end=source_slice.char_end,
        source_start_line=source_slice.source_start_line,
        source_start_column=source_slice.source_start_column,
        source_end_line=source_slice.source_end_line,
        view_sha256=hashlib.sha256(source_slice.view).hexdigest(),
        view_byte_length=len(source_slice.view),
        view_char_length=len(source_slice.view.decode("ascii")),
        view_line_count=len(line_starts),
        view_line_start_offsets=line_starts,
        view_line_byte_lengths=line_lengths,
        external_sources=external_sources,
    )


def _inline_source_manifest_entry(
    source: InlineJavaScriptSource, alias: str
) -> dict[str, Any]:
    return {
        "alias": alias,
        "path": source.path,
        "mode": source.mode,
        "stage": "0",
        "oid": source.oid,
        "source_sha256": source.source_sha256,
        "source_byte_start": source.byte_start,
        "source_byte_end_exclusive": source.byte_end,
        "source_char_start": source.source_char_start,
        "source_char_end_exclusive": source.source_char_end,
        "source_start_line": source.source_start_line,
        "source_start_column": source.source_start_column,
        "source_end_line": source.source_end_line,
        "view_byte_length": source.view_byte_length,
        "view_char_length": source.view_char_length,
        "view_line_count": source.view_line_count,
        "view_line_start_offsets": list(source.view_line_start_offsets),
        "view_line_byte_lengths": list(source.view_line_byte_lengths),
        "external_sources": [
            {"src": source_url, "path": source_path}
            for source_url, source_path in source.external_sources
        ],
        "view_sha256": source.view_sha256,
    }


def _verify_inline_external_sources(
    *,
    source_root: Path,
    source: InlineJavaScriptSource,
    source_manifest_by_path: dict[str, dict[str, str]],
    overlay_target_hashes: dict[str, str],
    ignore_matcher: Callable[[str], bool] | None,
) -> None:
    if source.external_sources and ignore_matcher is None:
        raise SemgrepGateError(
            "reviewed Semgrep ignore matcher is required for external script sources"
        )
    root = source_root.resolve(strict=True)
    for _source_url, path in source.external_sources:
        if ignore_matcher is not None and ignore_matcher(path):
            raise SemgrepGateError(
                f"external script source matches Semgrep ignore policy: {path}"
            )
        entry = source_manifest_by_path.get(path)
        if (
            entry is None
            or entry.get("stage") != "0"
            or entry.get("mode") not in {"100644", "100755"}
            or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", entry.get("oid", ""))
        ):
            raise SemgrepGateError(
                f"external script source lacks stage-zero identity: {path}"
            )
        external_path = source_root.joinpath(*PurePosixPath(path).parts)
        if (
            external_path.is_symlink()
            or external_path.is_junction()
            or not external_path.is_file()
        ):
            raise SemgrepGateError(
                f"external script source is missing, linked or non-regular: {path}"
            )
        try:
            external_path.resolve(strict=True).relative_to(root)
            content = external_path.read_bytes()
        except (OSError, ValueError) as exc:
            raise SemgrepGateError(
                f"cannot read external script source in stage-zero snapshot: {path}"
            ) from exc
        digest = hashlib.sha256(content).hexdigest()
        if (
            digest != entry["sha256"]
            or digest != overlay_target_hashes.get(path)
            or _stage_zero_blob_oid(content, entry["oid"]) != entry["oid"]
        ):
            raise SemgrepGateError(
                f"external script source differs from stage-zero snapshot: {path}"
            )


def _inline_javascript_scan_targets(
    scan_root: Path,
    overlay_target_hashes: dict[str, str],
    source_manifest: Sequence[dict[str, str]],
    ignore_matcher: Callable[[str], bool] | None,
) -> tuple[InlineJavaScriptSource, ...]:
    expected = set(REVIEWED_INLINE_JAVASCRIPT_PATHS)
    if any(not isinstance(entry, dict) for entry in source_manifest):
        raise SemgrepGateError("staged source manifest contains malformed entries")
    manifest_by_path = {entry.get("path"): entry for entry in source_manifest}
    if len(manifest_by_path) != len(source_manifest):
        raise SemgrepGateError("staged source manifest contains duplicate paths")
    snapshot_candidates = expected.intersection(manifest_by_path)
    overlay_candidates = expected.intersection(overlay_target_hashes)
    if not snapshot_candidates and not overlay_candidates:
        return ()
    if snapshot_candidates != expected or overlay_candidates != expected:
        raise SemgrepGateError(
            "inline JavaScript supplemental target set is incomplete"
        )
    if ignore_matcher is None:
        raise SemgrepGateError(
            "reviewed Semgrep ignore matcher is required for inline JavaScript targets"
        )
    root = scan_root.resolve(strict=True)
    sources: list[InlineJavaScriptSource] = []
    for index, path in enumerate(REVIEWED_INLINE_JAVASCRIPT_PATHS):
        alias = INLINE_JAVASCRIPT_ALIASES[index]
        for relative in (path, alias):
            if ignore_matcher(relative):
                raise SemgrepGateError(
                    f"inline JavaScript target unexpectedly matches Semgrep ignore policy: {relative}"
                )
        entry = manifest_by_path.get(path)
        if not isinstance(entry, dict):
            raise SemgrepGateError(
                f"inline JavaScript source lacks stage-zero identity: {path}"
            )
        source_path = scan_root.joinpath(*PurePosixPath(path).parts)
        if (
            source_path.is_symlink()
            or source_path.is_junction()
            or not source_path.is_file()
        ):
            raise SemgrepGateError(
                f"inline JavaScript source is missing, linked or non-regular: {path}"
            )
        try:
            source_path.resolve(strict=True).relative_to(root)
            content = source_path.read_bytes()
        except (OSError, ValueError) as exc:
            raise SemgrepGateError(
                f"cannot read inline JavaScript source inside scan root: {path}"
            ) from exc
        source = _derive_inline_javascript_source(path, entry, content)
        if overlay_target_hashes.get(path) != source.source_sha256:
            raise SemgrepGateError(
                f"inline JavaScript overlay differs from stage-zero source: {path}"
            )
        _verify_inline_external_sources(
            source_root=scan_root,
            source=source,
            source_manifest_by_path=manifest_by_path,
            overlay_target_hashes=overlay_target_hashes,
            ignore_matcher=ignore_matcher,
        )
        sources.append(source)
    return tuple(sources)


def _materialize_inline_javascript_inputs(
    *,
    source_root: Path,
    destination: Path,
    targets: Sequence[InlineJavaScriptSource],
    source_manifest: Sequence[dict[str, str]],
    overlay_target_hashes: dict[str, str],
    mapping_manifest_path: Path,
    source_snapshot_manifest_sha256: str,
    ignore_matcher: Callable[[str], bool] | None,
) -> tuple[tuple[str, ...], dict[str, InlineJavaScriptBinding], str]:
    if tuple(source.path for source in targets) != REVIEWED_INLINE_JAVASCRIPT_PATHS:
        raise SemgrepGateError("inline JavaScript projection target set is not exact")
    if not re.fullmatch(r"[0-9a-f]{64}", source_snapshot_manifest_sha256):
        raise SemgrepGateError("inline JavaScript source manifest digest is malformed")
    if any(not isinstance(entry, dict) for entry in source_manifest):
        raise SemgrepGateError("staged source manifest contains malformed entries")
    if (
        hashlib.sha256(_snapshot_manifest_bytes(source_manifest)).hexdigest()
        != source_snapshot_manifest_sha256
    ):
        raise SemgrepGateError(
            "inline JavaScript source manifest digest differs from staged entries"
        )
    if destination.exists() or destination.is_symlink() or destination.is_junction():
        raise SemgrepGateError("inline JavaScript projection destination is not fresh")
    root = source_root.resolve(strict=True)
    if destination.parent.resolve(strict=True) != root.parent:
        raise SemgrepGateError(
            "inline JavaScript projection must be a sibling of the staged scan root"
        )
    manifest_by_path = {entry.get("path"): entry for entry in source_manifest}
    if len(manifest_by_path) != len(source_manifest):
        raise SemgrepGateError("staged source manifest contains duplicate paths")
    destination.mkdir(parents=True)
    bindings: dict[str, InlineJavaScriptBinding] = {}
    projected_entries: list[dict[str, Any]] = []
    for index, source in enumerate(targets):
        entry = manifest_by_path.get(source.path)
        if (
            entry is None
            or entry.get("stage") != "0"
            or entry.get("mode") not in {"100644", "100755"}
            or entry.get("oid") != source.oid
            or entry.get("sha256") != source.source_sha256
        ):
            raise SemgrepGateError(
                f"inline JavaScript source lacks exact stage-zero identity: {source.path}"
            )
        path = source_root.joinpath(*PurePosixPath(source.path).parts)
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise SemgrepGateError(
                f"inline JavaScript source is missing, linked or non-regular: {source.path}"
            )
        try:
            path.resolve(strict=True).relative_to(root)
            content = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise SemgrepGateError(
                f"cannot read inline JavaScript source inside scan root: {source.path}"
            ) from exc
        actual_source = _derive_inline_javascript_source(source.path, entry, content)
        if actual_source != source or source.source_sha256 != overlay_target_hashes.get(
            source.path
        ):
            raise SemgrepGateError(
                f"inline JavaScript source differs from its stage-zero evidence: {source.path}"
            )
        _verify_inline_external_sources(
            source_root=source_root,
            source=source,
            source_manifest_by_path=manifest_by_path,
            overlay_target_hashes=overlay_target_hashes,
            ignore_matcher=ignore_matcher,
        )
        source_slice = _extract_reviewed_inline_script(content, source.path)
        view = source_slice.view
        alias = INLINE_JAVASCRIPT_ALIASES[index]
        alias_path = destination.joinpath(*PurePosixPath(alias).parts)
        alias_path.parent.mkdir()
        try:
            alias_path.write_bytes(view)
        except OSError as exc:
            raise SemgrepGateError(
                f"cannot materialize inline JavaScript parser alias: {source.path}"
            ) from exc
        binding = InlineJavaScriptBinding(
            alias=alias,
            path=source.path,
            source_mode=source.mode,
            source_oid=source.oid,
            source_sha256=source.source_sha256,
            source_start_line=source.source_start_line,
            source_start_column=source.source_start_column,
            source_byte_start=source.byte_start,
            source_byte_end=source.byte_end,
            source_char_start=source.source_char_start,
            source_char_end=source.source_char_end,
            source_end_line=source.source_end_line,
            view_byte_length=source.view_byte_length,
            view_char_length=source.view_char_length,
            view_line_count=source.view_line_count,
            view_line_start_offsets=source.view_line_start_offsets,
            view_line_byte_lengths=source.view_line_byte_lengths,
            external_sources=source.external_sources,
            view_sha256=source.view_sha256,
        )
        bindings[alias] = binding
        projected_entries.append(_inline_source_manifest_entry(source, alias))
    payload = (
        json.dumps(
            {
                "source_snapshot_manifest_sha256": source_snapshot_manifest_sha256,
                "targets": projected_entries,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    if (
        mapping_manifest_path.exists()
        or mapping_manifest_path.is_symlink()
        or mapping_manifest_path.is_junction()
    ):
        raise SemgrepGateError("inline JavaScript source mapping manifest is not fresh")
    try:
        mapping_manifest_path.write_bytes(payload)
    except OSError as exc:
        raise SemgrepGateError(
            "cannot write inline JavaScript source mapping manifest"
        ) from exc
    return INLINE_JAVASCRIPT_ALIASES, bindings, hashlib.sha256(payload).hexdigest()


def _verify_inline_javascript_inputs(
    *,
    source_root: Path,
    destination: Path,
    targets: Sequence[InlineJavaScriptSource],
    source_manifest: Sequence[dict[str, str]],
    overlay_target_hashes: dict[str, str],
    source_snapshot_manifest_sha256: str,
    mapping_manifest_path: Path,
    expected_mapping_manifest_sha256: str,
    ignore_matcher: Callable[[str], bool] | None,
) -> None:
    if tuple(source.path for source in targets) != REVIEWED_INLINE_JAVASCRIPT_PATHS:
        raise SemgrepGateError("inline JavaScript verification target set is not exact")
    if any(not isinstance(entry, dict) for entry in source_manifest):
        raise SemgrepGateError("staged source manifest contains malformed entries")
    if (
        mapping_manifest_path.is_symlink()
        or mapping_manifest_path.is_junction()
        or not mapping_manifest_path.is_file()
    ):
        raise SemgrepGateError("inline JavaScript source mapping manifest is missing")
    if (
        hashlib.sha256(_snapshot_manifest_bytes(source_manifest)).hexdigest()
        != source_snapshot_manifest_sha256
    ):
        raise SemgrepGateError(
            "inline JavaScript source manifest digest differs from staged entries"
        )
    try:
        manifest_bytes = mapping_manifest_path.read_bytes()
    except OSError as exc:
        raise SemgrepGateError(
            "cannot reread inline JavaScript source mapping manifest"
        ) from exc
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_mapping_manifest_sha256:
        raise SemgrepGateError("inline JavaScript source mapping manifest changed")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemgrepGateError(
            "inline JavaScript source mapping manifest is malformed"
        ) from exc
    expected_entries = [
        _inline_source_manifest_entry(source, INLINE_JAVASCRIPT_ALIASES[index])
        for index, source in enumerate(targets)
    ]
    if manifest != {
        "source_snapshot_manifest_sha256": source_snapshot_manifest_sha256,
        "targets": expected_entries,
    }:
        raise SemgrepGateError(
            "inline JavaScript source mapping manifest differs from the current run"
        )

    source_by_path = {entry.get("path"): entry for entry in source_manifest}
    if len(source_by_path) != len(source_manifest):
        raise SemgrepGateError("staged source manifest contains duplicate paths")
    source_root_resolved = source_root.resolve(strict=True)
    expected_alias_hashes: dict[str, str] = {}
    for source in targets:
        entry = source_by_path.get(source.path)
        if not isinstance(entry, dict):
            raise SemgrepGateError(
                f"inline JavaScript source lacks stage-zero identity: {source.path}"
            )
        path = source_root.joinpath(*PurePosixPath(source.path).parts)
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise SemgrepGateError(
                f"inline JavaScript source is missing, linked or non-regular: {source.path}"
            )
        try:
            path.resolve(strict=True).relative_to(source_root_resolved)
            content = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise SemgrepGateError(
                f"cannot reread inline JavaScript source: {source.path}"
            ) from exc
        actual_source = _derive_inline_javascript_source(source.path, entry, content)
        if actual_source != source or source.source_sha256 != overlay_target_hashes.get(
            source.path
        ):
            raise SemgrepGateError(
                f"inline JavaScript source changed during Semgrep: {source.path}"
            )
        _verify_inline_external_sources(
            source_root=source_root,
            source=source,
            source_manifest_by_path=source_by_path,
            overlay_target_hashes=overlay_target_hashes,
            ignore_matcher=ignore_matcher,
        )
        alias = INLINE_JAVASCRIPT_ALIASES[
            REVIEWED_INLINE_JAVASCRIPT_PATHS.index(source.path)
        ]
        alias_path = destination.joinpath(*PurePosixPath(alias).parts)
        if (
            alias_path.is_symlink()
            or alias_path.is_junction()
            or not alias_path.is_file()
        ):
            raise SemgrepGateError(
                "inline JavaScript parser alias is missing or linked"
            )
        try:
            alias_bytes = alias_path.read_bytes()
        except OSError as exc:
            raise SemgrepGateError(
                "cannot reread inline JavaScript parser alias"
            ) from exc
        source_slice = _extract_reviewed_inline_script(content, source.path)
        digest = hashlib.sha256(alias_bytes).hexdigest()
        if alias_bytes != source_slice.view or digest != source.view_sha256:
            raise SemgrepGateError(
                f"inline JavaScript parser alias differs from its source: {source.path}"
            )
        expected_alias_hashes[alias] = digest
    if (
        _tree_file_hashes(destination, description="inline JavaScript parser aliases")
        != expected_alias_hashes
    ):
        raise SemgrepGateError("inline JavaScript parser alias inventory changed")


def _dockerfile_scan_targets(
    scan_root: Path,
    overlay_target_hashes: dict[str, str],
    ignore_matcher: Callable[[str], bool] | None,
) -> tuple[str, ...]:
    """Select only the four reviewed Dockerfile targets missed by suffix detection."""

    candidates = set(overlay_target_hashes).intersection(
        REVIEWED_UNIGNORED_DOCKERFILE_TARGETS
    )
    if not candidates:
        return ()
    if candidates != REVIEWED_UNIGNORED_DOCKERFILE_TARGETS:
        missing = sorted(REVIEWED_UNIGNORED_DOCKERFILE_TARGETS - candidates)
        raise SemgrepGateError(
            "Dockerfile supplemental target set is incomplete: " + ", ".join(missing)
        )
    if ignore_matcher is None:
        raise SemgrepGateError(
            "reviewed Semgrep ignore matcher is required for Dockerfile targets"
        )

    root = scan_root.resolve(strict=True)
    targets: list[str] = []
    for relative in sorted(candidates):
        if ignore_matcher(relative):
            raise SemgrepGateError(
                f"reviewed Dockerfile target unexpectedly matches Semgrep ignore policy: {relative}"
            )
        target = scan_root.joinpath(*PurePosixPath(relative).parts)
        if target.is_symlink() or target.is_junction() or not target.is_file():
            raise SemgrepGateError(
                f"Dockerfile target is missing, linked or non-regular: {relative}"
            )
        try:
            target.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise SemgrepGateError(
                f"Dockerfile target escapes the scan root: {relative}"
            ) from exc
        digest = overlay_target_hashes.get(relative)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SemgrepGateError(
                f"Dockerfile target has malformed source hash evidence: {relative}"
            )
        targets.append(relative)
    return tuple(targets)


def _materialize_dockerfile_scan_inputs(
    *,
    source_root: Path,
    destination: Path,
    targets: Sequence[str],
    source_manifest: Sequence[dict[str, str]],
    overlay_target_hashes: dict[str, str],
    mapping_manifest_path: Path,
) -> tuple[tuple[str, ...], dict[str, str], str]:
    """Copy exact staged bytes to safe Dockerfile names and bind their identities."""

    if (
        len(targets) != len(REVIEWED_UNIGNORED_DOCKERFILE_TARGETS)
        or set(targets) != REVIEWED_UNIGNORED_DOCKERFILE_TARGETS
    ):
        raise SemgrepGateError("Dockerfile input projection target set is not exact")
    if destination.exists() or destination.is_symlink() or destination.is_junction():
        raise SemgrepGateError("Dockerfile input projection destination is not fresh")
    root = source_root.resolve(strict=True)
    try:
        if destination.parent.resolve(strict=True) != root.parent:
            raise SemgrepGateError(
                "Dockerfile input projection must be a sibling of the staged scan root"
            )
    except OSError as exc:
        raise SemgrepGateError(
            "Dockerfile input projection parent is unavailable"
        ) from exc
    manifest_by_path: dict[str, dict[str, str]] = {}
    for entry in source_manifest:
        if not isinstance(entry, dict):
            raise SemgrepGateError("staged source manifest has a malformed entry")
        relative = entry.get("path")
        if not isinstance(relative, str) or relative in manifest_by_path:
            raise SemgrepGateError(
                "staged source manifest has invalid Dockerfile entries"
            )
        manifest_by_path[relative] = entry

    destination.mkdir(parents=True)
    alias_to_source: dict[str, str] = {}
    projected_entries: list[dict[str, str]] = []
    for index, relative in enumerate(targets):
        entry = manifest_by_path.get(relative)
        if (
            entry is None
            or entry.get("mode") not in {"100644", "100755"}
            or not re.fullmatch(r"[0-9a-f]{40}", entry.get("oid", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", ""))
        ):
            raise SemgrepGateError(
                f"Dockerfile source lacks a regular stage-zero identity: {relative}"
            )
        source = source_root.joinpath(*PurePosixPath(relative).parts)
        if source.is_symlink() or source.is_junction() or not source.is_file():
            raise SemgrepGateError(
                f"Dockerfile source is missing, linked or non-regular: {relative}"
            )
        try:
            source.resolve(strict=True).relative_to(root)
            content = source.read_bytes()
        except (OSError, ValueError) as exc:
            raise SemgrepGateError(
                f"cannot read Dockerfile source inside scan root: {relative}"
            ) from exc
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry["sha256"] or digest != overlay_target_hashes.get(relative):
            raise SemgrepGateError(
                f"Dockerfile source bytes do not match stage-zero evidence: {relative}"
            )
        alias = f"target-{index:02d}/Dockerfile"
        alias_path = destination.joinpath(*PurePosixPath(alias).parts)
        alias_path.parent.mkdir()
        try:
            alias_path.write_bytes(content)
            if entry["mode"] == "100755":
                alias_path.chmod(0o755)
        except OSError as exc:
            raise SemgrepGateError(
                f"cannot materialize Dockerfile parser alias: {relative}"
            ) from exc
        alias_to_source[alias] = relative
        projected_entries.append(
            {
                "alias": alias,
                "path": relative,
                "mode": entry["mode"],
                "oid": entry["oid"],
                "sha256": digest,
            }
        )
    payload = (
        json.dumps(
            {"targets": projected_entries},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    if (
        mapping_manifest_path.exists()
        or mapping_manifest_path.is_symlink()
        or mapping_manifest_path.is_junction()
    ):
        raise SemgrepGateError("Dockerfile source mapping manifest is not fresh")
    try:
        mapping_manifest_path.write_bytes(payload)
    except OSError as exc:
        raise SemgrepGateError(
            "cannot write Dockerfile source mapping manifest"
        ) from exc
    return tuple(alias_to_source), alias_to_source, hashlib.sha256(payload).hexdigest()


def _logical_dockerfile_alias_path(path: Any, alias_to_source: dict[str, str]) -> str:
    normalized = _normalize_report_path(path)
    try:
        return alias_to_source[normalized]
    except KeyError as exc:
        raise SemgrepGateError(
            "Dockerfile supplemental report path is outside its alias set"
        ) from exc


def _remap_dockerfile_report_paths(
    report: dict[str, Any], alias_to_source: dict[str, str]
) -> dict[str, Any]:
    remapped = dict(report)
    paths = report.get("paths")
    if not isinstance(paths, dict):
        raise SemgrepGateError("Dockerfile supplemental report paths are malformed")
    remapped_paths = dict(paths)
    scanned = paths.get("scanned")
    if not isinstance(scanned, list):
        raise SemgrepGateError("Dockerfile supplemental scanned paths are malformed")
    remapped_paths["scanned"] = [
        _logical_dockerfile_alias_path(path, alias_to_source) for path in scanned
    ]
    remapped["paths"] = remapped_paths
    results = report.get("results")
    if not isinstance(results, list):
        raise SemgrepGateError("Dockerfile supplemental findings are malformed")
    remapped_results: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            raise SemgrepGateError("Dockerfile supplemental finding is malformed")
        copied_result = dict(result)
        copied_result["path"] = _logical_dockerfile_alias_path(
            result.get("path"), alias_to_source
        )
        remapped_results.append(copied_result)
    remapped["results"] = remapped_results
    return remapped


def _sarif_alias_path(uri: str, alias_to_source: dict[str, str]) -> str:
    parsed = urllib.parse.urlsplit(uri)
    path = urllib.parse.unquote(parsed.path) if parsed.scheme else uri
    if parsed.scheme and (
        parsed.scheme != "file"
        or parsed.netloc not in {"", "localhost"}
        or parsed.query
        or parsed.fragment
    ):
        raise SemgrepGateError("Dockerfile SARIF uses an unsupported artifact URI")
    if path.startswith("/src/"):
        path = path[len("/src/") :]
    elif path.startswith("/"):
        raise SemgrepGateError("Dockerfile SARIF artifact is outside the scan root")
    return _logical_dockerfile_alias_path(path, alias_to_source)


def _remap_dockerfile_sarif(
    sarif: dict[str, Any], alias_to_source: dict[str, str]
) -> dict[str, Any]:
    if sarif.get("version") != "2.1.0" or not isinstance(sarif.get("runs"), list):
        raise SemgrepGateError("Dockerfile SARIF report is malformed")
    remapped = json.loads(json.dumps(sarif))

    def visit(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            if parent_key in {"location", "artifactLocation"} and "uri" in value:
                uri = value.get("uri")
                if not isinstance(uri, str):
                    raise SemgrepGateError("Dockerfile SARIF artifact URI is malformed")
                value["uri"] = _sarif_alias_path(uri, alias_to_source)
            for key, child in value.items():
                visit(child, key)
        elif isinstance(value, list):
            for child in value:
                visit(child, parent_key)

    visit(remapped)
    return remapped


def _inline_binding_for_path(
    path: Any, bindings: dict[str, InlineJavaScriptBinding]
) -> InlineJavaScriptBinding:
    normalized = _normalize_report_path(path)
    try:
        return bindings[normalized]
    except KeyError as exc:
        raise SemgrepGateError(
            "inline JavaScript report path is outside its exact alias set"
        ) from exc


def _inline_offset_for_position(
    line: int, column: int, binding: InlineJavaScriptBinding
) -> int:
    if (
        not isinstance(line, int)
        or isinstance(line, bool)
        or not 1 <= line <= binding.view_line_count
        or not isinstance(column, int)
        or isinstance(column, bool)
        or column < 1
    ):
        raise SemgrepGateError("inline JavaScript position is malformed")
    line_index = line - 1
    if column > binding.view_line_byte_lengths[line_index] + 1:
        raise SemgrepGateError("inline JavaScript column is outside its slice")
    return binding.view_line_start_offsets[line_index] + column - 1


def _inline_line_column_for_offset(
    offset: int, binding: InlineJavaScriptBinding
) -> tuple[int, int]:
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or not 0 <= offset <= binding.view_byte_length
    ):
        raise SemgrepGateError("inline JavaScript offset is outside its slice")
    for index, (line_start, line_length) in enumerate(
        zip(
            binding.view_line_start_offsets,
            binding.view_line_byte_lengths,
            strict=True,
        )
    ):
        if line_start <= offset <= line_start + line_length:
            return index + 1, offset - line_start + 1
    raise SemgrepGateError("inline JavaScript offset does not map to a source line")


def _validate_inline_result_position(
    position: Any, binding: InlineJavaScriptBinding
) -> dict[str, int]:
    if not isinstance(position, dict):
        raise SemgrepGateError("inline JavaScript finding position is malformed")
    line = position.get("line")
    column = position.get("col")
    offset = position.get("offset")
    if (
        not isinstance(line, int)
        or isinstance(line, bool)
        or not 1 <= line <= binding.view_line_count
        or not isinstance(column, int)
        or isinstance(column, bool)
        or column < 1
        or not isinstance(offset, int)
        or isinstance(offset, bool)
        or not 0 <= offset <= binding.view_byte_length
    ):
        raise SemgrepGateError(
            "inline JavaScript finding position is outside its slice"
        )
    if _inline_offset_for_position(line, column, binding) != offset:
        raise SemgrepGateError(
            "inline JavaScript finding position disagrees with its byte offset"
        )
    if _inline_line_column_for_offset(offset, binding) != (line, column):
        raise SemgrepGateError(
            "inline JavaScript finding position disagrees with its byte offset"
        )
    return {"line": line, "col": column, "offset": offset}


def _validate_inline_javascript_supplement_report(
    report: dict[str, Any],
    aliases: Sequence[str],
    bindings: dict[str, InlineJavaScriptBinding],
    javascript_rule_ids: Sequence[str],
) -> None:
    expected = set(INLINE_JAVASCRIPT_ALIASES)
    if (
        tuple(aliases) != INLINE_JAVASCRIPT_ALIASES
        or set(bindings) != expected
        or {binding.alias for binding in bindings.values()} != expected
        or {binding.path for binding in bindings.values()}
        != set(REVIEWED_INLINE_JAVASCRIPT_PATHS)
        or not javascript_rule_ids
        or len(set(javascript_rule_ids)) != len(javascript_rule_ids)
    ):
        raise SemgrepGateError("inline JavaScript supplemental target set is not exact")
    errors = report.get("errors")
    skipped_rules = report.get("skipped_rules")
    results = report.get("results")
    paths = report.get("paths")
    scanned = paths.get("scanned") if isinstance(paths, dict) else None
    skipped = paths.get("skipped") if isinstance(paths, dict) else None
    timing = report.get("time")
    timeouts = timing.get("fixpoint_timeouts") if isinstance(timing, dict) else None
    if not isinstance(errors, list) or errors:
        raise SemgrepGateError(
            "inline JavaScript supplemental scan reported diagnostics"
        )
    if not isinstance(skipped_rules, list) or skipped_rules:
        raise SemgrepGateError("inline JavaScript supplemental scan skipped rules")
    if not isinstance(results, list):
        raise SemgrepGateError("inline JavaScript supplemental scan has no result list")
    if not isinstance(scanned, list) or not isinstance(skipped, list):
        raise SemgrepGateError(
            "inline JavaScript supplemental scan has malformed path evidence"
        )
    normalized_scanned = [_normalize_report_path(path) for path in scanned]
    if (
        len(normalized_scanned) != len(set(normalized_scanned))
        or set(normalized_scanned) != expected
    ):
        raise SemgrepGateError(
            "inline JavaScript supplemental scan did not scan the exact target set"
        )
    if skipped:
        raise SemgrepGateError("inline JavaScript supplemental scan skipped a target")
    if not isinstance(timeouts, list) or timeouts:
        raise SemgrepGateError(
            "inline JavaScript supplemental scan has missing or timed-out analysis"
        )
    allowed_rules = {f"out.{rule_id}" for rule_id in javascript_rule_ids}
    for result in results:
        if not isinstance(result, dict):
            raise SemgrepGateError(
                "inline JavaScript supplemental finding is malformed"
            )
        binding = _inline_binding_for_path(result.get("path"), bindings)
        rule_id = result.get("check_id")
        if not isinstance(rule_id, str) or rule_id not in allowed_rules:
            raise SemgrepGateError(
                "inline JavaScript supplemental finding is outside the selected rules"
            )
        start = _validate_inline_result_position(result.get("start"), binding)
        end = _validate_inline_result_position(result.get("end"), binding)
        if end["offset"] < start["offset"] or end["line"] < start["line"]:
            raise SemgrepGateError("inline JavaScript finding range is reversed")


def _remap_inline_javascript_report(
    report: dict[str, Any], bindings: dict[str, InlineJavaScriptBinding]
) -> dict[str, Any]:
    remapped = dict(report)
    paths = report.get("paths")
    if not isinstance(paths, dict):
        raise SemgrepGateError("inline JavaScript report paths are malformed")
    scanned = paths.get("scanned")
    if not isinstance(scanned, list):
        raise SemgrepGateError("inline JavaScript scanned paths are malformed")
    remapped_paths = dict(paths)
    remapped_paths["scanned"] = [
        _inline_binding_for_path(path, bindings).path for path in scanned
    ]
    remapped["paths"] = remapped_paths
    results = report.get("results")
    if not isinstance(results, list):
        raise SemgrepGateError("inline JavaScript findings are malformed")
    remapped_results: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            raise SemgrepGateError("inline JavaScript finding is malformed")
        binding = _inline_binding_for_path(result.get("path"), bindings)
        copied = dict(result)
        copied["path"] = binding.path
        for field in ("start", "end"):
            position = _validate_inline_result_position(result.get(field), binding)
            mapped = dict(result[field])
            mapped["line"] = position["line"] + binding.source_start_line - 1
            if position["line"] == 1:
                mapped["col"] = position["col"] + binding.source_start_column - 1
            mapped["offset"] = position["offset"] + binding.source_byte_start
            copied[field] = mapped
        remapped_results.append(copied)
    remapped["results"] = remapped_results
    return remapped


def _map_inline_sarif_region(region: Any, binding: InlineJavaScriptBinding) -> None:
    if not isinstance(region, dict):
        raise SemgrepGateError("inline JavaScript SARIF region is malformed")
    start_line = region.get("startLine")
    end_line = region.get("endLine")
    start_column = region.get("startColumn")
    end_column = region.get("endColumn")
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= binding.view_line_count
        for value in (start_line, end_line)
    ):
        raise SemgrepGateError("inline JavaScript SARIF line is outside its slice")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 1
        for value in (start_column, end_column)
    ):
        raise SemgrepGateError("inline JavaScript SARIF column is malformed")

    start_offset = _inline_offset_for_position(start_line, start_column, binding)
    end_offset = _inline_offset_for_position(end_line, end_column, binding)
    if end_offset < start_offset:
        raise SemgrepGateError("inline JavaScript SARIF region is reversed")

    for offset_key, length_key, view_length, source_start in (
        (
            "byteOffset",
            "byteLength",
            binding.view_byte_length,
            binding.source_byte_start,
        ),
        (
            "charOffset",
            "charLength",
            binding.view_char_length,
            binding.source_char_start,
        ),
    ):
        offset = region.get(offset_key)
        length = region.get(length_key)
        if offset is None and length is None:
            continue
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or offset < 0
            or not isinstance(length, int)
            or isinstance(length, bool)
            or length < 0
        ):
            raise SemgrepGateError(
                f"inline JavaScript SARIF {offset_key[:-6]} range is malformed"
            )
        if offset > view_length or offset + length > view_length:
            raise SemgrepGateError(
                f"inline JavaScript SARIF {offset_key[:-6]} range is outside its slice"
            )
        if offset != start_offset or offset + length != end_offset:
            raise SemgrepGateError(
                f"inline JavaScript SARIF {offset_key[:-6]} range disagrees with coordinates"
            )
        region[offset_key] = offset + source_start

    region["startLine"] = start_line + binding.source_start_line - 1
    region["endLine"] = end_line + binding.source_start_line - 1
    if start_line == 1:
        region["startColumn"] = start_column + binding.source_start_column - 1
    if end_line == 1:
        region["endColumn"] = end_column + binding.source_start_column - 1


def _remap_inline_javascript_sarif(
    sarif: dict[str, Any],
    bindings: dict[str, InlineJavaScriptBinding],
    javascript_typescript_rule_ids: Sequence[str],
    javascript_rule_ids: Sequence[str],
) -> dict[str, Any]:
    if sarif.get("version") != "2.1.0" or not isinstance(sarif.get("runs"), list):
        raise SemgrepGateError("inline JavaScript SARIF report is malformed")
    if not sarif["runs"]:
        raise SemgrepGateError("inline JavaScript SARIF report has no runs")
    expected_all_rules = {
        f"out.{rule_id}" for rule_id in javascript_typescript_rule_ids
    }
    allowed_results = {f"out.{rule_id}" for rule_id in javascript_rule_ids}
    remapped = json.loads(json.dumps(sarif))

    def visit(
        value: Any,
        parent_key: str = "",
        artifact_logical_paths: Sequence[str] | None = None,
    ) -> None:
        if isinstance(value, dict):
            if parent_key in {"artifactLocation", "location"} and "uriBaseId" in value:
                raise SemgrepGateError(
                    "inline JavaScript SARIF artifact URI base is unsupported"
                )
            if parent_key == "artifactLocation":
                uri = value.get("uri")
                artifact_index = value.get("index")
                if artifact_index is not None:
                    if (
                        artifact_logical_paths is None
                        or not isinstance(artifact_index, int)
                        or isinstance(artifact_index, bool)
                        or not 0 <= artifact_index < len(artifact_logical_paths)
                    ):
                        raise SemgrepGateError(
                            "inline JavaScript SARIF artifact index has no exact inventory"
                        )
                    if not isinstance(uri, str):
                        raise SemgrepGateError(
                            "inline JavaScript SARIF artifact index has no direct URI"
                        )
                    indexed_path = artifact_logical_paths[artifact_index]
                    direct_path = _sarif_alias_path(
                        uri,
                        {alias: binding.path for alias, binding in bindings.items()},
                    )
                    if indexed_path != direct_path:
                        raise SemgrepGateError(
                            "inline JavaScript SARIF artifact URI contradicts its index"
                        )
            if parent_key in {"location", "artifactLocation"} and "uri" in value:
                uri = value.get("uri")
                if not isinstance(uri, str):
                    raise SemgrepGateError(
                        "inline JavaScript SARIF artifact URI is malformed"
                    )
                logical = _sarif_alias_path(
                    uri, {alias: binding.path for alias, binding in bindings.items()}
                )
                value["uri"] = logical
            if parent_key == "physicalLocation":
                artifact = value.get("artifactLocation")
                if not isinstance(artifact, dict) or not isinstance(
                    artifact.get("uri"), str
                ):
                    raise SemgrepGateError(
                        "inline JavaScript SARIF finding has no exact artifact URI"
                    )
                alias = _sarif_alias_path(
                    artifact["uri"],
                    {key: binding.path for key, binding in bindings.items()},
                )
                binding = next(
                    binding for binding in bindings.values() if binding.path == alias
                )
                if not isinstance(value.get("region"), dict):
                    raise SemgrepGateError(
                        "inline JavaScript SARIF finding has no region"
                    )
                _map_inline_sarif_region(value["region"], binding)
            for key, child in value.items():
                visit(child, key, artifact_logical_paths)
        elif isinstance(value, list):
            for child in value:
                visit(child, parent_key, artifact_logical_paths)

    for run in remapped["runs"]:
        if not isinstance(run, dict):
            raise SemgrepGateError("inline JavaScript SARIF run is malformed")
        tool = run.get("tool")
        driver = tool.get("driver") if isinstance(tool, dict) else None
        rules = driver.get("rules") if isinstance(driver, dict) else None
        if not isinstance(rules, list):
            raise SemgrepGateError("inline JavaScript SARIF rule metadata is missing")
        reported_rules = [rule.get("id") for rule in rules if isinstance(rule, dict)]
        if (
            len(reported_rules) != len(rules)
            or any(not isinstance(rule_id, str) for rule_id in reported_rules)
            or len(reported_rules) != len(set(reported_rules))
            or set(reported_rules) != expected_all_rules
        ):
            raise SemgrepGateError(
                "inline JavaScript SARIF rules differ from the selected config"
            )
        results = run.get("results")
        if not isinstance(results, list):
            raise SemgrepGateError("inline JavaScript SARIF results are malformed")
        artifacts_present = "artifacts" in run
        artifacts = run.get("artifacts")
        if artifacts_present and not isinstance(artifacts, list):
            raise SemgrepGateError("inline JavaScript SARIF artifacts are malformed")
        artifact_logical_paths: list[str] | None = [] if artifacts_present else None
        for artifact in artifacts or []:
            location = artifact.get("location") if isinstance(artifact, dict) else None
            uri = location.get("uri") if isinstance(location, dict) else None
            if not isinstance(uri, str):
                raise SemgrepGateError(
                    "inline JavaScript SARIF artifact URI is malformed"
                )
            logical_path = _sarif_alias_path(
                uri,
                {alias: binding.path for alias, binding in bindings.items()},
            )
            if logical_path not in {binding.path for binding in bindings.values()}:
                raise SemgrepGateError(
                    "inline JavaScript SARIF artifact is outside its source set"
                )
            if artifact_logical_paths is None:
                raise SemgrepGateError(
                    "inline JavaScript SARIF artifact inventory is malformed"
                )
            artifact_logical_paths.append(logical_path)
        for result in results:
            rule_id = result.get("ruleId") if isinstance(result, dict) else None
            rule_index = result.get("ruleIndex") if isinstance(result, dict) else None
            if (
                not isinstance(result, dict)
                or rule_id not in allowed_results
                or (
                    rule_index is not None
                    and (
                        not isinstance(rule_index, int)
                        or isinstance(rule_index, bool)
                        or not 0 <= rule_index < len(reported_rules)
                        or reported_rules[rule_index] != rule_id
                    )
                )
            ):
                raise SemgrepGateError(
                    "inline JavaScript SARIF result is outside the selected rules"
                )
            locations = result.get("locations")
            if not isinstance(locations, list) or not locations:
                raise SemgrepGateError(
                    "inline JavaScript SARIF result has no locations"
                )
            for location in locations:
                physical = (
                    location.get("physicalLocation")
                    if isinstance(location, dict)
                    else None
                )
                artifact = (
                    physical.get("artifactLocation")
                    if isinstance(physical, dict)
                    else None
                )
                if (
                    not isinstance(artifact, dict)
                    or not isinstance(artifact.get("uri"), str)
                    or not isinstance(physical.get("region"), dict)
                ):
                    raise SemgrepGateError(
                        "inline JavaScript SARIF result location is incomplete"
                    )
        visit(run, artifact_logical_paths=artifact_logical_paths)
    return remapped


def _write_new_json_report(path: Path, report: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink() or path.is_junction():
        raise SemgrepGateError(f"Semgrep report destination is not fresh: {path.name}")
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        path.write_text(payload, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise SemgrepGateError(
            f"cannot write Semgrep report {path.name}: {exc}"
        ) from exc


def _write_dockerfile_rules_config(
    selected_config_path: Path, destination: Path
) -> tuple[str, tuple[str, ...]]:
    """Project only the reviewed Dockerfile rule without changing its path semantics."""

    if selected_config_path.is_symlink() or selected_config_path.is_junction():
        raise SemgrepGateError("selected Semgrep config may not be linked")
    try:
        if not selected_config_path.is_file():
            raise SemgrepGateError("selected Semgrep config is missing")
        source = json.loads(selected_config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemgrepGateError(f"cannot read selected Semgrep config: {exc}") from exc
    if not isinstance(source, dict) or set(source) != {"rules"}:
        raise SemgrepGateError("selected Semgrep config has an unsupported shape")
    rules = source.get("rules")
    if not isinstance(rules, list):
        raise SemgrepGateError("selected Semgrep config has no rule list")
    dockerfile_rules: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise SemgrepGateError("selected Semgrep config contains a malformed rule")
        rule_id = rule.get("id")
        languages = rule.get("languages")
        if (
            not isinstance(rule_id, str)
            or not rule_id
            or not isinstance(languages, list)
            or any(not isinstance(language, str) for language in languages)
        ):
            raise SemgrepGateError(
                "selected Semgrep config contains an invalid rule identity"
            )
        if "dockerfile" in languages:
            if rule_id != DOCKERFILE_RULE_ID or languages != ["dockerfile"]:
                raise SemgrepGateError(
                    "selected Semgrep config has an unreviewed Dockerfile rule"
                )
            if rule.get("paths") is not None:
                raise SemgrepGateError(
                    "Dockerfile supplemental scan cannot preserve a rule path filter"
                )
            dockerfile_rules.append(rule)
    if len(dockerfile_rules) != 1:
        raise SemgrepGateError(
            "selected Semgrep config must contain exactly the reviewed Dockerfile rule"
        )
    if destination.is_symlink() or destination.is_junction() or destination.exists():
        raise SemgrepGateError("Dockerfile Semgrep config destination is not fresh")
    payload = (
        json.dumps(
            {"rules": dockerfile_rules},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    try:
        destination.write_bytes(payload)
    except OSError as exc:
        raise SemgrepGateError(
            f"cannot write Dockerfile Semgrep config: {exc}"
        ) from exc
    return hashlib.sha256(payload).hexdigest(), (DOCKERFILE_RULE_ID,)


def _normalize_report_path(path: Any) -> str:
    if not isinstance(path, str) or not path:
        raise SemgrepGateError("Semgrep report target path is malformed")
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise SemgrepGateError("Semgrep report target path is not repository-relative")
    return pure.as_posix()


def _validate_inline_external_source_coverage(
    targets: Sequence[InlineJavaScriptSource], scanned_paths: Sequence[Any]
) -> None:
    scanned = {_normalize_report_path(path) for path in scanned_paths}
    required = {
        source_path
        for source in targets
        for _source_url, source_path in source.external_sources
    }
    missing = sorted(required - scanned)
    if missing:
        raise SemgrepGateError(
            "external script source is not covered by the primary or MTS scan: "
            + ", ".join(missing)
        )


def _read_semgrep_report(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise SemgrepGateError(f"Semgrep report is missing or linked: {path.name}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemgrepGateError(
            f"cannot read Semgrep report {path.name}: {exc}"
        ) from exc
    if not isinstance(report, dict):
        raise SemgrepGateError(f"Semgrep report root is not an object: {path.name}")
    return report


def _validate_mts_supplement_report(
    report: dict[str, Any], targets: Sequence[str]
) -> None:
    expected = set(targets)
    if not expected:
        raise SemgrepGateError("MTS supplemental scan has no targets")
    errors = report.get("errors")
    skipped_rules = report.get("skipped_rules")
    results = report.get("results")
    paths = report.get("paths")
    scanned = paths.get("scanned") if isinstance(paths, dict) else None
    skipped = paths.get("skipped") if isinstance(paths, dict) else None
    timing = report.get("time")
    timeouts = timing.get("fixpoint_timeouts") if isinstance(timing, dict) else None
    if not isinstance(errors, list) or errors:
        raise SemgrepGateError("MTS supplemental scan reported diagnostics")
    if not isinstance(skipped_rules, list) or skipped_rules:
        raise SemgrepGateError("MTS supplemental scan skipped rules")
    if not isinstance(results, list):
        raise SemgrepGateError("MTS supplemental scan has no result list")
    if not isinstance(scanned, list) or not isinstance(skipped, list):
        raise SemgrepGateError("MTS supplemental scan has malformed path evidence")
    normalized_scanned = [_normalize_report_path(path) for path in scanned]
    if (
        len(normalized_scanned) != len(set(normalized_scanned))
        or set(normalized_scanned) != expected
    ):
        raise SemgrepGateError(
            "MTS supplemental scan did not scan the exact target set"
        )
    if skipped:
        raise SemgrepGateError("MTS supplemental scan skipped an explicit target")
    if not isinstance(timeouts, list) or timeouts:
        raise SemgrepGateError(
            "MTS supplemental scan has missing or timed-out analysis"
        )
    for result in results:
        if (
            not isinstance(result, dict)
            or _normalize_report_path(result.get("path")) not in expected
        ):
            raise SemgrepGateError("MTS supplemental finding is outside its target set")


def _merge_semgrep_reports(
    primary: dict[str, Any],
    supplemental: dict[str, Any],
    *,
    targets: Sequence[str],
    javascript_typescript_config_sha256: str,
    javascript_typescript_rule_ids: Sequence[str],
    supplemental_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine the supplementary findings and target evidence with primary JSON."""

    merged = dict(primary)
    for key in ("results", "errors", "skipped_rules"):
        left = primary.get(key)
        right = supplemental.get(key)
        if not isinstance(left, list) or not isinstance(right, list):
            raise SemgrepGateError(f"Semgrep report list field is malformed: {key}")
        merged[key] = [*left, *right]
    primary_paths = primary.get("paths")
    supplemental_paths = supplemental.get("paths")
    if not isinstance(primary_paths, dict) or not isinstance(supplemental_paths, dict):
        raise SemgrepGateError("Semgrep report paths are malformed")
    primary_scanned = primary_paths.get("scanned")
    supplemental_scanned = supplemental_paths.get("scanned")
    primary_skipped = primary_paths.get("skipped")
    supplemental_skipped = supplemental_paths.get("skipped")
    if any(
        not isinstance(value, list)
        for value in (
            primary_scanned,
            supplemental_scanned,
            primary_skipped,
            supplemental_skipped,
        )
    ):
        raise SemgrepGateError("Semgrep report path evidence is malformed")
    normalized_primary = [_normalize_report_path(path) for path in primary_scanned]
    normalized_supplemental = [
        _normalize_report_path(path) for path in supplemental_scanned
    ]
    if len(normalized_primary) != len(set(normalized_primary)):
        raise SemgrepGateError("primary Semgrep scan reported duplicate targets")
    if set(normalized_primary) & set(normalized_supplemental):
        label = "MTS" if supplemental_evidence is None else "supplemental"
        raise SemgrepGateError(f"primary and {label} Semgrep scans overlap targets")
    merged_paths = dict(primary_paths)
    merged_paths["scanned"] = [*primary_scanned, *supplemental_scanned]
    merged_paths["skipped"] = [*primary_skipped, *supplemental_skipped]
    merged["paths"] = merged_paths
    primary_time = primary.get("time")
    supplemental_time = supplemental.get("time")
    if not isinstance(primary_time, dict) or not isinstance(supplemental_time, dict):
        raise SemgrepGateError("Semgrep report timing metadata is malformed")
    existing_evidence = primary.get("supplemental_scan_evidence", [])
    if not isinstance(existing_evidence, list) or any(
        not isinstance(entry, dict) for entry in existing_evidence
    ):
        raise SemgrepGateError("Semgrep supplemental scan evidence is malformed")
    new_evidence = supplemental_evidence or {
        "mode": "explicit-unknown-extension-typescript",
        "targets": list(targets),
        "javascript_typescript_config_sha256": javascript_typescript_config_sha256,
        "javascript_typescript_rule_ids": list(javascript_typescript_rule_ids),
        "time": supplemental_time,
    }
    merged["supplemental_scan_evidence"] = [*existing_evidence, new_evidence]
    return merged


def _validate_dockerfile_supplement_report(
    report: dict[str, Any],
    alias_targets: Sequence[str],
    alias_to_source: dict[str, str],
) -> None:
    expected = set(alias_targets)
    expected_mapping = {
        f"target-{index:02d}/Dockerfile": target
        for index, target in enumerate(sorted(REVIEWED_UNIGNORED_DOCKERFILE_TARGETS))
    }
    if (
        not expected
        or len(expected) != len(alias_targets)
        or alias_to_source != expected_mapping
        or set(alias_to_source) != expected
        or set(alias_to_source.values()) != REVIEWED_UNIGNORED_DOCKERFILE_TARGETS
        or any(
            not re.fullmatch(r"target-[0-9]{2}/Dockerfile", alias) for alias in expected
        )
    ):
        raise SemgrepGateError("Dockerfile supplemental target set is not exact")
    errors = report.get("errors")
    skipped_rules = report.get("skipped_rules")
    results = report.get("results")
    paths = report.get("paths")
    scanned = paths.get("scanned") if isinstance(paths, dict) else None
    skipped = paths.get("skipped") if isinstance(paths, dict) else None
    timing = report.get("time")
    timeouts = timing.get("fixpoint_timeouts") if isinstance(timing, dict) else None
    if not isinstance(errors, list) or errors:
        raise SemgrepGateError("Dockerfile supplemental scan reported diagnostics")
    if not isinstance(skipped_rules, list) or skipped_rules:
        raise SemgrepGateError("Dockerfile supplemental scan skipped rules")
    if not isinstance(results, list):
        raise SemgrepGateError("Dockerfile supplemental scan has no result list")
    if not isinstance(scanned, list) or not isinstance(skipped, list):
        raise SemgrepGateError(
            "Dockerfile supplemental scan has malformed path evidence"
        )
    normalized_scanned = [_normalize_report_path(path) for path in scanned]
    if (
        len(normalized_scanned) != len(set(normalized_scanned))
        or set(normalized_scanned) != expected
    ):
        raise SemgrepGateError(
            "Dockerfile supplemental scan did not scan the exact target set"
        )
    if skipped:
        raise SemgrepGateError(
            "Dockerfile supplemental scan skipped an explicit target"
        )
    if not isinstance(timeouts, list) or timeouts:
        raise SemgrepGateError(
            "Dockerfile supplemental scan has missing or timed-out analysis"
        )
    for result in results:
        if not isinstance(result, dict):
            raise SemgrepGateError("Dockerfile supplemental finding is malformed")
        if _normalize_report_path(result.get("path")) not in expected:
            raise SemgrepGateError(
                "Dockerfile supplemental finding is outside its target set"
            )
        rule_id = result.get("check_id")
        if (
            not isinstance(rule_id, str)
            or rule_id.removeprefix("out.") != DOCKERFILE_RULE_ID
        ):
            raise SemgrepGateError(
                "Dockerfile supplemental finding is outside the selected rule"
            )


def _merge_sarif_reports(
    primary: dict[str, Any], supplemental: dict[str, Any]
) -> dict[str, Any]:
    if primary.get("version") != "2.1.0" or supplemental.get("version") != "2.1.0":
        raise SemgrepGateError("Semgrep SARIF report version is unsupported")
    primary_runs = primary.get("runs")
    supplemental_runs = supplemental.get("runs")
    if not isinstance(primary_runs, list) or not isinstance(supplemental_runs, list):
        raise SemgrepGateError("Semgrep SARIF report runs are malformed")
    if not primary_runs or not supplemental_runs:
        raise SemgrepGateError("Semgrep SARIF report has no runs")
    merged = dict(primary)
    merged["runs"] = [*primary_runs, *supplemental_runs]
    return merged


def _write_merged_semgrep_report(
    path: Path, report: dict[str, Any], *, format_name: str
) -> None:
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise SemgrepGateError(
            f"Semgrep {format_name} output path is missing or linked: {path.name}"
        )
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    file_descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        stream = os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n")
        file_descriptor = None
        with stream:
            stream.write(payload)
        if (
            temporary_path.is_symlink()
            or temporary_path.is_junction()
            or not temporary_path.is_file()
        ):
            raise SemgrepGateError(
                "temporary merged Semgrep report is missing or linked"
            )
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise SemgrepGateError(
                f"Semgrep {format_name} output path is missing or linked: {path.name}"
            )
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise SemgrepGateError(
            f"cannot write merged Semgrep {format_name}: {exc}"
        ) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise SemgrepGateError(
                    f"cannot remove temporary merged Semgrep {format_name}: {exc}"
                ) from exc


def _write_semgrep_json(path: Path, report: dict[str, Any]) -> None:
    _write_merged_semgrep_report(path, report, format_name="JSON")


def _write_semgrep_sarif(path: Path, report: dict[str, Any]) -> None:
    _write_merged_semgrep_report(path, report, format_name="SARIF")


def _workflow_rules_commit(repository_root: Path) -> str:
    workflow_path = repository_root / ".github" / "workflows" / "ci.yml"
    try:
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise SemgrepGateError(f"cannot read the Semgrep workflow pin: {exc}") from exc
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    semgrep_job = jobs.get("semgrep-sast") if isinstance(jobs, dict) else None
    steps = semgrep_job.get("steps") if isinstance(semgrep_job, dict) else None
    if not isinstance(steps, list):
        raise SemgrepGateError("CI does not declare the Semgrep SAST steps")

    matching_steps = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        with_values = step.get("with")
        if (
            isinstance(with_values, dict)
            and with_values.get("repository") == RULES_REPOSITORY
        ):
            matching_steps.append(with_values)
    if len(matching_steps) != 1:
        raise SemgrepGateError(
            "CI must check out the pinned Semgrep rules repository exactly once"
        )
    commit = matching_steps[0].get("ref")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        raise SemgrepGateError(
            "CI Semgrep rules ref must be a full lowercase commit SHA"
        )
    return commit


def _precommit_semgrep_image(repository_root: Path) -> str:
    config_path = repository_root / ".pre-commit-config.yaml"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise SemgrepGateError(
            f"cannot read the staged pre-commit Semgrep hook: {exc}"
        ) from exc
    repos = config.get("repos") if isinstance(config, dict) else None
    if not isinstance(repos, list):
        raise SemgrepGateError("staged pre-commit configuration has no repository list")
    matching_hooks: list[dict[str, Any]] = []
    for repo in repos:
        if not isinstance(repo, dict) or repo.get("repo") != "local":
            continue
        hooks = repo.get("hooks")
        if not isinstance(hooks, list):
            continue
        matching_hooks.extend(
            hook
            for hook in hooks
            if isinstance(hook, dict) and hook.get("id") == "semgrep-docker"
        )
    if len(matching_hooks) != 1:
        raise SemgrepGateError(
            "staged pre-commit configuration must define one local semgrep-docker hook"
        )
    entry = matching_hooks[0].get("entry")
    expected_prefix = [
        "uv",
        "run",
        "--frozen",
        "python",
        "-I",
        "scripts/quality/run_semgrep_gate.py",
    ]
    if not isinstance(entry, str):
        raise SemgrepGateError("staged Semgrep hook entry is not a command")
    command_parts = entry.split()
    if (
        len(command_parts) != len(expected_prefix) + 1
        or command_parts[:-1] != expected_prefix
    ):
        raise SemgrepGateError(
            "staged Semgrep hook entry does not match the shared runner"
        )
    image = command_parts[-1]
    if not IMAGE_PATTERN.fullmatch(image):
        raise SemgrepGateError("staged Semgrep hook image is not digest-pinned")
    return image


def _git_common_directory(
    repository_root: Path, *, command_runner: CommandRunner
) -> Path:
    try:
        result = command_runner(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SemgrepGateError(
            f"cannot locate the Git common directory: {exc}"
        ) from exc
    common_dir_text = result.stdout.strip()
    if result.returncode != 0 or not common_dir_text:
        detail = (result.stderr or "").strip()
        suffix = f": {detail}" if detail else ""
        raise SemgrepGateError(f"cannot locate the Git common directory{suffix}")
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = repository_root / common_dir
    try:
        return common_dir.resolve(strict=True)
    except OSError as exc:
        raise SemgrepGateError(f"Git common directory is unavailable: {exc}") from exc


def _run_git(
    command: list[str],
    *,
    cwd: Path,
    command_runner: CommandRunner,
) -> subprocess.CompletedProcess[str]:
    try:
        result = command_runner(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SemgrepGateError(
            f"could not check out pinned Semgrep rules: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise SemgrepGateError(
            f"pinned Semgrep rules command failed ({result.returncode}){suffix}"
        )
    return result


def _checkout_rules(
    commit: str,
    destination: Path,
    *,
    command_runner: CommandRunner,
) -> Path:
    """Fetch the CI-pinned commit and safely extract its archive without checkout."""

    destination.mkdir()
    _run_git(["git", "init", "--quiet"], cwd=destination, command_runner=command_runner)
    _run_git(
        ["git", "remote", "add", "origin", RULES_URL],
        cwd=destination,
        command_runner=command_runner,
    )
    _run_git(
        ["git", "fetch", "--quiet", "--depth=1", "origin", commit],
        cwd=destination,
        command_runner=command_runner,
    )
    head = _run_git(
        ["git", "rev-parse", "FETCH_HEAD^{commit}"],
        cwd=destination,
        command_runner=command_runner,
    ).stdout.strip()
    if head != commit:
        raise SemgrepGateError("fetched Semgrep rules do not match the CI pin")
    try:
        archive_result = command_runner(
            ["git", "archive", "--format=tar", "FETCH_HEAD"],
            cwd=destination,
            check=False,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SemgrepGateError(f"cannot archive pinned Semgrep rules: {exc}") from exc
    if archive_result.returncode != 0:
        detail = archive_result.stderr or b""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        suffix = f": {detail.strip()}" if detail else ""
        raise SemgrepGateError(
            f"cannot archive pinned Semgrep rules ({archive_result.returncode}){suffix}"
        )
    archive_bytes = archive_result.stdout
    if isinstance(archive_bytes, str):
        archive_bytes = archive_bytes.encode("utf-8")
    if not isinstance(archive_bytes, bytes) or not archive_bytes:
        raise SemgrepGateError("pinned Semgrep rules archive is empty or malformed")
    rules_root = destination / "rules"
    rules_root.mkdir()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
            seen: set[str] = set()
            for member in archive.getmembers():
                member_name = (
                    member.name.removesuffix("/")
                    if member.isdir() and member.name.endswith("/")
                    else member.name
                )
                relative = PurePosixPath(member_name)
                if (
                    not member_name
                    or "\\" in member_name
                    or relative.is_absolute()
                    or PureWindowsPath(member_name).drive
                    or ".." in relative.parts
                    or relative.as_posix() != member_name
                    or member_name in seen
                ):
                    raise SemgrepGateError(
                        f"invalid path in pinned Semgrep rules archive: {member.name!r}"
                    )
                seen.add(member_name)
                target = rules_root.joinpath(*relative.parts)
                if not target.resolve().is_relative_to(rules_root.resolve()):
                    raise SemgrepGateError(
                        f"rules archive path escapes its destination: {member.name}"
                    )
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise SemgrepGateError(
                        f"unsupported entry in pinned Semgrep rules archive: {member.name}"
                    )
                content = archive.extractfile(member)
                if content is None:
                    raise SemgrepGateError(
                        f"cannot read pinned Semgrep rule file: {member.name}"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                with content, target.open("wb") as output_stream:
                    shutil.copyfileobj(content, output_stream)
    except (OSError, tarfile.TarError) as exc:
        raise SemgrepGateError(
            f"cannot extract pinned Semgrep rules archive: {exc}"
        ) from exc
    return rules_root


def _read_index_entries(
    repository_root: Path, *, command_runner: CommandRunner
) -> list[IndexEntry]:
    """Read and validate the exact regular-file entries staged for commit."""

    try:
        result = command_runner(
            ["git", "ls-files", "--stage", "-z"],
            cwd=repository_root,
            check=False,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SemgrepGateError(
            f"cannot read the tracked Semgrep targets: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = result.stderr or result.stdout or b""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        detail = str(detail).strip()
        suffix = f": {detail}" if detail else ""
        raise SemgrepGateError(
            f"cannot read the tracked Semgrep targets ({result.returncode}){suffix}"
        )

    raw_output = result.stdout
    if isinstance(raw_output, str):
        raw_output = raw_output.encode("utf-8")
    if not isinstance(raw_output, bytes) or (
        raw_output and not raw_output.endswith(b"\0")
    ):
        raise SemgrepGateError("git returned malformed staged Semgrep entries")

    entries: list[IndexEntry] = []
    seen: set[str] = set()
    raw_entries = raw_output.split(b"\0")
    for raw_entry in raw_entries[:-1] if raw_output else ():
        metadata, separator, raw_path = raw_entry.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3:
            raise SemgrepGateError("git returned a malformed staged Semgrep entry")
        try:
            mode = fields[0].decode("ascii")
            oid = fields[1].decode("ascii")
            stage_text = fields[2].decode("ascii")
        except UnicodeDecodeError as exc:
            raise SemgrepGateError("Git index metadata is not ASCII") from exc
        if mode not in ("100644", "100755"):
            raise SemgrepGateError(
                f"staged Semgrep target has an unsupported file mode: {mode}"
            )
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid):
            raise SemgrepGateError("Git index contains a malformed object id")
        if stage_text != "0":
            raise SemgrepGateError("Git index contains an unresolved merge entry")
        try:
            path_text = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SemgrepGateError("staged Semgrep paths must be valid UTF-8") from exc
        relative = PurePosixPath(path_text)
        if (
            not path_text
            or "\\" in path_text
            or relative.is_absolute()
            or PureWindowsPath(path_text).drive
            or ".." in relative.parts
            or relative.as_posix() != path_text
        ):
            raise SemgrepGateError(f"invalid staged Semgrep target path: {path_text!r}")
        if path_text in seen:
            raise SemgrepGateError(f"duplicate staged Semgrep target: {path_text}")
        seen.add(path_text)
        if relative.name == ".semgrepignore" and path_text != ".semgrepignore":
            raise SemgrepGateError(
                f"nested Semgrep ignore files are not allowed: {path_text}"
            )
        entries.append(IndexEntry(relative, mode, oid, 0))
    if ".semgrepignore" not in seen:
        raise SemgrepGateError("staged targets do not include the root .semgrepignore")
    _validate_windows_path_collisions(entries)
    return entries


def _index_blobs(
    entries: Sequence[IndexEntry],
    *,
    repository_root: Path,
    command_runner: CommandRunner,
) -> dict[str, bytes]:
    """Read every staged blob through one bounded Git batch invocation."""

    object_ids = list(dict.fromkeys(entry.oid for entry in entries))
    if not object_ids:
        raise SemgrepGateError("Git index contains no staged Semgrep blobs")
    request = ("\n".join(object_ids) + "\n").encode("ascii")
    try:
        result = command_runner(
            ["git", "cat-file", "--batch"],
            cwd=repository_root,
            check=False,
            capture_output=True,
            input=request,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SemgrepGateError(f"cannot read staged Semgrep blobs: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr or result.stdout or b""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        suffix = f": {str(detail).strip()}" if detail else ""
        raise SemgrepGateError(
            f"cannot read staged Semgrep blobs ({result.returncode}){suffix}"
        )
    raw_output = result.stdout
    if isinstance(raw_output, str):
        raw_output = raw_output.encode("utf-8")
    if not isinstance(raw_output, bytes):
        raise SemgrepGateError("git returned malformed staged blob data")

    blobs: dict[str, bytes] = {}
    cursor = 0
    for expected_oid in object_ids:
        header_end = raw_output.find(b"\n", cursor)
        if header_end < 0:
            raise SemgrepGateError("git returned truncated staged blob data")
        header = raw_output[cursor:header_end]
        try:
            object_id, object_type, size_text = header.decode("ascii").split(" ")
            size = int(size_text)
        except (UnicodeDecodeError, ValueError) as exc:
            raise SemgrepGateError(
                "git returned a malformed staged blob header"
            ) from exc
        if object_id != expected_oid or object_type != "blob" or size < 0:
            raise SemgrepGateError("Git returned an unexpected staged object")
        data_start = header_end + 1
        data_end = data_start + size
        if data_end >= len(raw_output) or raw_output[data_end : data_end + 1] != b"\n":
            raise SemgrepGateError("git returned truncated staged blob contents")
        content = raw_output[data_start:data_end]
        git_object = b"blob " + str(size).encode("ascii") + b"\0" + content
        object_hash = hashlib.new(
            "sha1" if len(expected_oid) == 40 else "sha256",
            git_object,
            usedforsecurity=False,
        ).hexdigest()
        if object_hash != expected_oid:
            raise SemgrepGateError(
                "Git returned staged blob bytes with a wrong object id"
            )
        blobs[expected_oid] = content
        cursor = data_end + 1
    if cursor != len(raw_output):
        raise SemgrepGateError("git returned unexpected trailing staged blob data")
    return blobs


def _create_scan_snapshot(
    repository_root: Path,
    destination: Path,
    *,
    command_runner: CommandRunner,
) -> tuple[Path, list[dict[str, str]], list[IndexEntry]]:
    """Materialize the exact stage-zero index blobs in a disposable scan root."""

    if destination.exists() or destination.is_symlink() or destination.is_junction():
        raise SemgrepGateError("Semgrep scan snapshot destination already exists")
    entries = _read_index_entries(repository_root, command_runner=command_runner)
    blobs = _index_blobs(
        entries, repository_root=repository_root, command_runner=command_runner
    )
    destination.mkdir()
    manifest: list[dict[str, str]] = []
    for entry in entries:
        relative = entry.path
        content = blobs[entry.oid]
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(content)
            if entry.mode == "100755":
                target.chmod(0o755)
        except OSError as exc:
            raise SemgrepGateError(
                f"cannot materialize staged Semgrep target {relative.as_posix()}: {exc}"
            ) from exc
        manifest.append(
            {
                "path": relative.as_posix(),
                "mode": entry.mode,
                "oid": entry.oid,
                "stage": str(entry.stage),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return destination, manifest, entries


def _indexed_manifest(
    repository_root: Path, *, command_runner: CommandRunner
) -> list[IndexEntry]:
    """Return the index identities for the pre/post-scan integrity comparison."""

    return _read_index_entries(repository_root, command_runner=command_runner)


def _index_digest(entries: Sequence[IndexEntry]) -> str:
    payload = json.dumps(
        [entry.identity() for entry in entries], separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _changed_index_paths(
    expected: Sequence[IndexEntry], actual: Sequence[IndexEntry]
) -> list[str]:
    expected_by_path = {entry.path.as_posix(): entry.identity() for entry in expected}
    actual_by_path = {entry.path.as_posix(): entry.identity() for entry in actual}
    return sorted(
        path
        for path in expected_by_path.keys() | actual_by_path.keys()
        if expected_by_path.get(path) != actual_by_path.get(path)
    )


def _write_snapshot_manifest(manifest: list[dict[str, str]], destination: Path) -> str:
    raw = _snapshot_manifest_bytes(manifest)
    path = destination / "semgrep-targets.json"
    try:
        if path.is_symlink() or path.is_junction():
            raise SemgrepGateError("Semgrep target manifest path is linked")
        path.write_bytes(raw)
    except OSError as exc:
        raise SemgrepGateError(f"cannot write Semgrep target manifest: {exc}") from exc
    return hashlib.sha256(raw).hexdigest()


def _tree_file_hashes(root: Path, *, description: str) -> dict[str, str]:
    if root.is_symlink() or root.is_junction() or not root.is_dir():
        raise SemgrepGateError(f"{description} root is missing or linked")
    hashes: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise SemgrepGateError(f"{description} contains a linked path: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SemgrepGateError(f"{description} contains a non-regular path: {path}")
        relative = path.relative_to(root).as_posix()
        if relative in hashes:
            raise SemgrepGateError(
                f"{description} contains a duplicate path: {relative}"
            )
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as exc:
            raise SemgrepGateError(
                f"cannot read {description} file {relative}: {exc}"
            ) from exc
        hashes[relative] = digest.hexdigest()
    return hashes


def _verify_source_snapshot(
    source_root: Path, source_manifest: Sequence[dict[str, str]]
) -> dict[str, str]:
    expected: dict[str, str] = {}
    for entry in source_manifest:
        relative = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise SemgrepGateError("staged source manifest is malformed")
        if relative in expected:
            raise SemgrepGateError(f"duplicate staged source manifest path: {relative}")
        expected[relative] = digest
    actual = _tree_file_hashes(source_root, description="stage-zero snapshot")
    if actual != expected:
        changed = sorted(
            path
            for path in actual.keys() | expected.keys()
            if actual.get(path) != expected.get(path)
        )
        raise SemgrepGateError(
            "stage-zero snapshot changed during rendered-target preparation: "
            + ", ".join(changed[:20])
        )
    return actual


def _load_overlay_helper(source_root: Path) -> Any:
    helper_path = (
        source_root / "scripts" / "quality" / "helm_rendered_target_overlay.py"
    )
    if (
        helper_path.is_symlink()
        or helper_path.is_junction()
        or not helper_path.is_file()
    ):
        raise SemgrepGateError(
            "staged Helm rendered-target helper is missing or linked"
        )
    module_name = f"_ue_helm_rendered_target_overlay_{uuid.uuid4().hex}"
    try:
        source = helper_path.read_bytes()
        loader = _SnapshotSourceLoader(module_name, helper_path, source)
        specification = importlib.util.spec_from_loader(
            module_name, loader, origin=str(helper_path)
        )
        if specification is None:
            raise ImportError("cannot load the staged Helm rendered-target helper")
        module = importlib.util.module_from_spec(specification)
        sys.modules[module_name] = module
        loader.exec_module(module)
    except (ImportError, OSError, SyntaxError, AttributeError) as exc:
        raise SemgrepGateError(
            f"staged Helm rendered-target helper is unavailable: {exc}"
        ) from exc
    finally:
        sys.modules.pop(module_name, None)
    if not isinstance(getattr(module, "HelmOverlayError", None), type):
        raise SemgrepGateError("staged Helm helper has no HelmOverlayError type")
    required_callables = (
        "helm_archive_pin",
        "verify_helm_archive",
        "prepare_overlay",
        "bounded_process_runner",
    )
    if any(not callable(getattr(module, name, None)) for name in required_callables):
        raise SemgrepGateError("staged Helm helper has an incomplete runner API")
    return module


class _SnapshotSourceLoader(importlib.machinery.SourceFileLoader):
    """Load only the verified snapshot source bytes, without reading or writing pyc."""

    def __init__(self, fullname: str, path: Path, source: bytes) -> None:
        super().__init__(fullname, str(path))
        self._snapshot_source = source

    def get_code(self, fullname: str) -> Any:
        if fullname != self.name:
            raise ImportError("snapshot loader was requested for another module")
        return self.source_to_code(self._snapshot_source, self.path, _optimize=-1)


def _validated_helm_archive_pin(pin: Any) -> dict[str, str]:
    required = {
        "platform_key",
        "version",
        "archive_url",
        "archive_sha256",
        "archive_type",
        "archive_member",
        "executable_name",
    }
    if not isinstance(pin, dict) or set(pin) != required:
        raise SemgrepGateError("staged Helm helper returned a malformed archive pin")
    platform_key = pin.get("platform_key")
    version = pin.get("version")
    archive_type = pin.get("archive_type")
    archive_url = pin.get("archive_url")
    archive_sha256 = pin.get("archive_sha256")
    if (
        not isinstance(platform_key, str)
        or platform_key not in {"linux-amd64", "windows-amd64"}
        or not isinstance(version, str)
        or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version)
        or not isinstance(archive_type, str)
        or archive_type not in {"tar.gz", "zip"}
        or (platform_key == "linux-amd64") != (archive_type == "tar.gz")
        or (platform_key == "windows-amd64") != (archive_type == "zip")
        or not isinstance(archive_url, str)
        or not isinstance(archive_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", archive_sha256)
    ):
        raise SemgrepGateError("staged Helm helper returned an invalid archive pin")
    expected_url = (
        f"https://{HELM_ARCHIVE_HOST}/helm-{version}-{platform_key}.{archive_type}"
    )
    if archive_url != expected_url:
        raise SemgrepGateError(
            "pinned Helm archive URL is not the canonical official release URL"
        )
    if (
        pin.get("archive_member")
        != f"{platform_key}/{'helm.exe' if platform_key == 'windows-amd64' else 'helm'}"
        or pin.get("executable_name")
        != ("helm.exe" if platform_key == "windows-amd64" else "helm")
    ):
        raise SemgrepGateError("staged Helm helper returned an invalid archive member")
    return {key: str(value) for key, value in pin.items()}


def _validate_helm_archive_url(url: str, *, expected_url: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        expected = urllib.parse.urlsplit(expected_url)
        port = parsed.port
    except ValueError as exc:
        raise SemgrepGateError("Helm archive server returned an invalid URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != HELM_ARCHIVE_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or parsed.path != expected.path
        or parsed.hostname != expected.hostname
    ):
        raise SemgrepGateError(
            "Helm archive download redirected outside its pinned HTTPS URL"
        )


def _download_helm_archive(pin: dict[str, str], destination: Path) -> Path:
    """Stream a bounded, TLS-verified official archive and verify its pinned hash."""

    pin = _validated_helm_archive_pin(pin)
    if destination.exists() or destination.is_symlink() or destination.is_junction():
        raise SemgrepGateError("Helm archive download destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    created_by_runner = False
    deadline = time.monotonic() + HELM_ARCHIVE_TIMEOUT_SECONDS * (
        HELM_ARCHIVE_MAX_REDIRECTS + 1
    )
    try:
        current_url = pin["archive_url"]
        for redirect_count in range(HELM_ARCHIVE_MAX_REDIRECTS + 1):
            _validate_helm_archive_url(current_url, expected_url=pin["archive_url"])
            parsed_url = urllib.parse.urlsplit(current_url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SemgrepGateError("Helm archive download exceeded its time limit")
            connection = http.client.HTTPSConnection(
                HELM_ARCHIVE_HOST,
                port=443,
                timeout=min(HELM_ARCHIVE_TIMEOUT_SECONDS, remaining),
                context=ssl.create_default_context(),
            )
            try:
                connection.request(
                    "GET",
                    parsed_url.path,
                    headers={"User-Agent": "university-ecosystem-semgrep-gate"},
                )
                response = connection.getresponse()
                if 300 <= response.status < 400:
                    location = response.getheader("Location")
                    if location is None or redirect_count == HELM_ARCHIVE_MAX_REDIRECTS:
                        raise SemgrepGateError(
                            "Helm archive server returned an invalid redirect"
                        )
                    current_url = urllib.parse.urljoin(current_url, location)
                    _validate_helm_archive_url(
                        current_url, expected_url=pin["archive_url"]
                    )
                    continue
                if response.status != 200:
                    raise SemgrepGateError(
                        "Helm archive server returned a non-success status"
                    )
                content_length = response.getheader("Content-Length")
                if content_length is not None and (
                    not content_length.isdecimal()
                    or int(content_length) > HELM_ARCHIVE_MAX_BYTES
                ):
                    raise SemgrepGateError(
                        "Helm archive response exceeds the size limit"
                    )
                with destination.open("xb") as output:
                    created_by_runner = True
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise SemgrepGateError(
                                "Helm archive download exceeded its time limit"
                            )
                        if connection.sock is not None:
                            connection.sock.settimeout(remaining)
                        else:
                            _set_response_socket_timeout(response, remaining)
                        chunk = response.read(HELM_ARCHIVE_CHUNK_BYTES)
                        if time.monotonic() > deadline:
                            raise SemgrepGateError(
                                "Helm archive download exceeded its time limit"
                            )
                        if not chunk:
                            break
                        if not isinstance(chunk, bytes):
                            raise SemgrepGateError(
                                "Helm archive server returned non-byte data"
                            )
                        total += len(chunk)
                        if total > HELM_ARCHIVE_MAX_BYTES:
                            raise SemgrepGateError(
                                "Helm archive response exceeds the size limit"
                            )
                        digest.update(chunk)
                        output.write(chunk)
                break
            finally:
                connection.close()
        else:
            raise SemgrepGateError("Helm archive redirect limit exceeded")
    except (SemgrepGateError, http.client.HTTPException, OSError) as exc:
        if (
            created_by_runner
            and destination.exists()
            and not destination.is_symlink()
            and not destination.is_junction()
        ):
            try:
                destination.unlink()
            except OSError:
                pass
        if isinstance(exc, SemgrepGateError):
            raise
        raise SemgrepGateError(
            f"cannot download the pinned Helm archive: {exc}"
        ) from exc
    if total == 0 or digest.hexdigest() != pin["archive_sha256"]:
        if not destination.is_symlink() and not destination.is_junction():
            destination.unlink()
        raise SemgrepGateError(
            "downloaded Helm archive does not match its pinned SHA-256"
        )
    return destination


def _set_response_socket_timeout(response: Any, timeout_seconds: float) -> None:
    """Apply the remaining download deadline to an HTTP response socket."""

    candidates = [response]
    for _ in range(4):
        current = candidates[-1]
        for attribute in ("fp", "raw"):
            nested = getattr(current, attribute, None)
            if nested is not None and nested not in candidates:
                candidates.append(nested)
    for candidate in candidates:
        for attribute in ("_sock", "sock"):
            response_socket = getattr(candidate, attribute, None)
            if response_socket is not None:
                response_socket.settimeout(timeout_seconds)
                return
    raise SemgrepGateError(
        "cannot enforce the Helm archive download deadline on its response"
    )


def _validate_prefetched_helm_archive(
    archive_path: Path, *, pin: dict[str, str], source_root: Path
) -> Path:
    archive_input = Path(archive_path)
    if archive_input.is_symlink() or archive_input.is_junction():
        raise SemgrepGateError("prefetched Helm archive may not be linked")
    try:
        archive = archive_input.resolve(strict=True)
        archive.relative_to(source_root.resolve(strict=True))
    except ValueError:
        pass
    except OSError as exc:
        raise SemgrepGateError(
            f"prefetched Helm archive is unavailable: {exc}"
        ) from exc
    else:
        raise SemgrepGateError(
            "prefetched Helm archive may not be inside the scan snapshot"
        )
    if not archive.is_file() or archive.stat().st_size > HELM_ARCHIVE_MAX_BYTES:
        raise SemgrepGateError("prefetched Helm archive is not a bounded regular file")
    if _sha256_file(archive) != pin["archive_sha256"]:
        raise SemgrepGateError(
            "prefetched Helm archive does not match its pinned SHA-256"
        )
    return archive


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise SemgrepGateError(f"cannot hash Helm archive: {exc}") from exc
    return digest.hexdigest()


def _chart_template_sources(source_root: Path) -> set[str]:
    found: set[str] = set()
    allowed = tuple(PurePosixPath(root).parts for root in HELM_TEMPLATE_ROOTS)
    for path in source_root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise SemgrepGateError(f"linked path in stage-zero snapshot: {path}")
        if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        relative = PurePosixPath(path.relative_to(source_root).as_posix())
        parts = relative.parts
        if len(parts) < 3 or parts[0] != "charts" or "templates" not in parts:
            continue
        if not any(parts[: len(root)] == root for root in allowed):
            raise SemgrepGateError(
                "unreviewed chart YAML template root in stage snapshot: "
                + relative.as_posix()
            )
        found.add(relative.as_posix())
    if len(found) != 40:
        raise SemgrepGateError(
            f"staged Helm template inventory must contain exactly 40 YAML files; found {len(found)}"
        )
    return found


def _validate_overlay_provenance(
    *,
    source_root: Path,
    overlay_root: Path,
    source_manifest: Sequence[dict[str, str]],
    source_manifest_sha256: str,
    provenance: Any,
    archive_pin: dict[str, str],
    helm_tool: Any,
) -> dict[str, str]:
    if not isinstance(provenance, dict):
        raise SemgrepGateError("Helm helper returned malformed provenance")
    if provenance.get("source_snapshot_manifest_sha256") != source_manifest_sha256:
        raise SemgrepGateError("Helm provenance is not bound to the stage manifest")

    staged = {entry["path"]: entry for entry in source_manifest}
    registry_path = "scripts/quality/helm_semgrep_profile_registry.json"
    registry_entry = staged.get(registry_path)
    if (
        registry_entry is None
        or provenance.get("profile_registry_path") != registry_path
        or provenance.get("profile_registry_sha256") != registry_entry.get("sha256")
    ):
        raise SemgrepGateError(
            "Helm provenance is not bound to the staged profile registry"
        )
    if (
        provenance.get("helm_version") != archive_pin.get("version")
        or provenance.get("helm_platform_key") != archive_pin.get("platform_key")
        or provenance.get("helm_archive_sha256") != archive_pin.get("archive_sha256")
        or provenance.get("helm_binary_sha256")
        != getattr(helm_tool, "binary_sha256", None)
        or getattr(helm_tool, "version", None) != archive_pin.get("version")
        or getattr(helm_tool, "platform_key", None) != archive_pin.get("platform_key")
    ):
        raise SemgrepGateError(
            "Helm provenance does not match the verified pinned binary"
        )
    template_sources = provenance.get("template_sources")
    if not isinstance(template_sources, list) or len(template_sources) != 40:
        raise SemgrepGateError(
            "Helm provenance must contain exactly 40 template sources"
        )
    discovered = _chart_template_sources(source_root)
    declared_templates: dict[str, dict[str, Any]] = {}
    for source in template_sources:
        if not isinstance(source, dict):
            raise SemgrepGateError("Helm template provenance row is malformed")
        path = source.get("path")
        if not isinstance(path, str) or path in declared_templates:
            raise SemgrepGateError(
                "Helm template provenance path is missing or duplicated"
            )
        declared_templates[path] = source
    if set(declared_templates) != discovered:
        raise SemgrepGateError(
            "Helm provenance does not match the staged template inventory"
        )
    for path, source in declared_templates.items():
        entry = staged.get(path)
        if (
            entry is None
            or source.get("source_sha256") != entry.get("sha256")
            or source.get("git_blob_oid") != entry.get("oid")
        ):
            raise SemgrepGateError(f"Helm template provenance is stale: {path}")

    guard_paths = provenance.get("guard_only_sources")
    if not isinstance(guard_paths, list) or set(guard_paths) != HELM_GUARD_ONLY_PATHS:
        raise SemgrepGateError("Helm provenance guard-only source set is not exact")
    if any(
        declared_templates[path].get("role") != "guard-only"
        for path in HELM_GUARD_ONLY_PATHS
    ) or any(
        source.get("role") != "resource"
        for path, source in declared_templates.items()
        if path not in HELM_GUARD_ONLY_PATHS
    ):
        raise SemgrepGateError("Helm template resource/guard roles are inconsistent")

    profiles = provenance.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != len(HELM_PROFILE_NAMES):
        raise SemgrepGateError("Helm provenance must contain exactly eight profiles")
    profile_views: dict[str, tuple[str, str]] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            raise SemgrepGateError("Helm profile provenance row is malformed")
        name = profile.get("name")
        view_path = profile.get("view_path")
        view_sha256 = profile.get("view_sha256")
        if (
            not isinstance(name, str)
            or name not in HELM_PROFILE_NAMES
            or name in profile_views
            or view_path != f"charts/rendered-profiles/{name}.yaml"
            or not isinstance(view_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", view_sha256)
        ):
            raise SemgrepGateError("Helm profile path or identity is not approved")
        profile_views[name] = (view_path, view_sha256)
    if set(profile_views) != HELM_PROFILE_NAMES:
        raise SemgrepGateError("Helm profile set is incomplete or unexpected")

    target_rows = provenance.get("targets")
    if not isinstance(target_rows, list):
        raise SemgrepGateError("Helm helper returned no final overlay target manifest")
    target_hashes: dict[str, str] = {}
    target_origins: dict[str, str] = {}
    target_index_fields: dict[str, dict[str, Any]] = {}
    for row in target_rows:
        if not isinstance(row, dict):
            raise SemgrepGateError("overlay target manifest row is malformed")
        path = row.get("path")
        digest = row.get("sha256")
        origin = row.get("origin")
        relative = PurePosixPath(path) if isinstance(path, str) else None
        if (
            relative is None
            or not path
            or "\\" in path
            or relative.is_absolute()
            or PureWindowsPath(path).drive
            or ".." in relative.parts
            or relative.as_posix() != path
            or path in target_hashes
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(origin, str)
        ):
            raise SemgrepGateError(
                "overlay target manifest has an invalid path or digest"
            )
        target_hashes[path] = digest
        target_origins[path] = origin
        target_index_fields[path] = row

    generated_paths = {view_path for view_path, _digest in profile_views.values()}
    if any(path in staged for path in generated_paths):
        raise SemgrepGateError("a rendered profile would replace a staged input")
    expected_paths = (set(staged) - discovered) | generated_paths
    if set(target_hashes) != expected_paths:
        raise SemgrepGateError(
            "Helm overlay changed the staged target set unexpectedly"
        )
    for path in set(staged) - discovered:
        entry = staged[path]
        row = target_index_fields[path]
        if (
            target_origins[path] != "staged-index"
            or target_hashes[path] != entry["sha256"]
            or row.get("mode") != entry["mode"]
            or row.get("oid") != entry["oid"]
            or row.get("stage") != entry["stage"]
        ):
            raise SemgrepGateError(
                f"non-template staged input changed in Helm overlay: {path}"
            )
    for name, (path, digest) in profile_views.items():
        if (
            target_hashes.get(path) != digest
            or target_origins.get(path) != f"helm-profile:{name}"
        ):
            raise SemgrepGateError(
                f"rendered profile target provenance mismatch: {name}"
            )

    actual_hashes = _tree_file_hashes(overlay_root, description="rendered scan overlay")
    if actual_hashes != target_hashes:
        changed = sorted(
            path
            for path in actual_hashes.keys() | target_hashes.keys()
            if actual_hashes.get(path) != target_hashes.get(path)
        )
        raise SemgrepGateError(
            "rendered scan overlay differs from its provenance: "
            + ", ".join(changed[:20])
        )
    return target_hashes


def _write_overlay_manifest(provenance: dict[str, Any], destination: Path) -> str:
    payload = (
        json.dumps(provenance, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    raw = payload.encode("utf-8")
    path = destination / "semgrep-rendered-target-overlay.json"
    try:
        if path.is_symlink() or path.is_junction():
            raise SemgrepGateError("rendered overlay manifest path is linked")
        path.write_bytes(raw)
    except OSError as exc:
        raise SemgrepGateError(
            f"cannot write rendered overlay manifest: {exc}"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _write_consistency_summary(
    destination: Path,
    *,
    status: str,
    target_count: int,
    manifest_sha256: str,
    index_before_sha256: str,
    index_after_sha256: str | None,
    changed_paths: list[str] | None = None,
) -> None:
    summary: dict[str, Any] = {
        "status": status,
        "target_count": target_count,
        "manifest_sha256": manifest_sha256,
        "index_before_sha256": index_before_sha256,
        "index_after_sha256": index_after_sha256,
    }
    if changed_paths:
        summary["changed_paths"] = changed_paths
    path = destination / "semgrep-targets-consistency.json"
    try:
        if path.is_symlink() or path.is_junction():
            raise SemgrepGateError("Semgrep target consistency path is linked")
        path.write_text(
            json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise SemgrepGateError(
            f"cannot write Semgrep consistency summary: {exc}"
        ) from exc


def _docker_scan(
    *,
    scan_root: Path,
    output_directory: Path,
    image: str,
    command_runner: CommandRunner,
    scan_id: str = "semgrep",
    config_name: str = "security-rules.json",
    report_prefix: str = "semgrep",
    target_paths: Sequence[str] = (".",),
    scan_unknown_extensions: bool = False,
    scan_dockerfile_aliases: bool = False,
    scan_inline_javascript_aliases: bool = False,
    timeout_seconds: int = SCAN_TIMEOUT_SECONDS,
) -> int:
    if (
        not re.fullmatch(r"[a-z0-9-]+", scan_id)
        or not re.fullmatch(r"[a-z0-9-]+", report_prefix)
        or Path(config_name).name != config_name
        or not target_paths
    ):
        raise SemgrepGateError(
            "Semgrep scan identity or target configuration is malformed"
        )
    if (
        sum(
            (
                scan_unknown_extensions,
                scan_dockerfile_aliases,
                scan_inline_javascript_aliases,
            )
        )
        > 1
    ):
        raise SemgrepGateError("Semgrep scan target modes are mutually exclusive")
    if scan_unknown_extensions:
        if "." in target_paths:
            raise SemgrepGateError(
                "unknown-extension scan requires explicit file targets"
            )
        for relative in target_paths:
            path = PurePosixPath(relative)
            if path.is_absolute() or any(
                part in {"", ".", ".."} for part in path.parts
            ):
                raise SemgrepGateError("unknown-extension scan target is not relative")
            target = scan_root.joinpath(*path.parts)
            if target.is_symlink() or target.is_junction() or not target.is_file():
                raise SemgrepGateError(
                    f"unknown-extension scan target is missing or linked: {relative}"
                )
    elif scan_dockerfile_aliases:
        expected_aliases = tuple(
            f"target-{index:02d}/Dockerfile"
            for index in range(len(REVIEWED_UNIGNORED_DOCKERFILE_TARGETS))
        )
        if tuple(target_paths) != expected_aliases:
            raise SemgrepGateError("Dockerfile alias target set is not exact")
        for relative in expected_aliases:
            path = PurePosixPath(relative)
            if (
                path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
                or path.name != "Dockerfile"
                or not re.fullmatch(r"target-[0-9]{2}", path.parent.as_posix())
            ):
                raise SemgrepGateError("Dockerfile alias target is malformed")
            target = scan_root.joinpath(*path.parts)
            if target.is_symlink() or target.is_junction() or not target.is_file():
                raise SemgrepGateError(
                    f"Dockerfile alias target is missing or linked: {relative}"
                )
    elif scan_inline_javascript_aliases:
        if tuple(target_paths) != INLINE_JAVASCRIPT_ALIASES:
            raise SemgrepGateError("inline JavaScript alias target set is not exact")
        for relative in INLINE_JAVASCRIPT_ALIASES:
            path = PurePosixPath(relative)
            if (
                path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
                or path.name != "inline.js"
                or not re.fullmatch(r"target-[0-9]{2}", path.parent.as_posix())
            ):
                raise SemgrepGateError("inline JavaScript alias target is malformed")
            target = scan_root.joinpath(*path.parts)
            if target.is_symlink() or target.is_junction() or not target.is_file():
                raise SemgrepGateError(
                    f"inline JavaScript alias target is missing or linked: {relative}"
                )
    elif tuple(target_paths) != (".",):
        raise SemgrepGateError(
            "primary Semgrep scan must keep its repository-root target"
        )
    container_name = f"ue-r9-semgrep-luna-{uuid.uuid4().hex}"
    cid_file = output_directory.parent / f"{scan_id}.cid"
    if cid_file.exists() or cid_file.is_symlink() or cid_file.is_junction():
        raise SemgrepGateError("Semgrep container id path already exists")
    command = [
        "docker",
        "run",
        "--name",
        container_name,
        "--cidfile",
        cid_file.as_posix(),
        "--cpus=2",
        "--memory=3g",
        "--memory-swap=3g",
        "--read-only",
        "--tmpfs",
        f"{CONTAINER_TMP}:rw,nosuid,nodev,size=512m",
        "-e",
        f"HOME={CONTAINER_TMP}",
        "-e",
        f"SEMGREP_LOG_FILE={CONTAINER_TMP}/semgrep.log",
        "-e",
        f"SEMGREP_VERSION_CACHE_PATH={CONTAINER_TMP}/semgrep-cache",
        "-v",
        f"{scan_root.as_posix()}:/src:ro",
        "-v",
        f"{output_directory.as_posix()}:/out",
        "-w",
        "/src",
        image,
        "sh",
        "-c",
        f'mkdir -p {CONTAINER_TMP}/.semgrep && exec semgrep "$@"',
        "semgrep",
        "--metrics",
        "off",
        "--disable-version-check",
        "--oss-only",
        "--error",
        "--disable-nosem",
        "--no-git-ignore",
        "--verbose",
        "--max-target-bytes=0",
        "--jobs",
        "2",
        "--config",
        f"/out/{config_name}",
    ]
    if scan_unknown_extensions:
        command.append("--scan-unknown-extensions")
    command.extend(
        [
            f"--json-output=/out/{report_prefix}.json",
            f"--sarif-output=/out/{report_prefix}.sarif",
            *target_paths,
        ]
    )
    try:
        result = command_runner(
            command,
            cwd=scan_root,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        scan_error: OSError | subprocess.TimeoutExpired | None = exc
        result = None
    else:
        scan_error = None

    container_id = None
    cidfile_id = None
    if cid_file.exists() or cid_file.is_symlink() or cid_file.is_junction():
        if cid_file.is_symlink() or cid_file.is_junction() or not cid_file.is_file():
            raise SemgrepGateError("Semgrep container id file is not a regular file")
        try:
            cidfile_id = cid_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise SemgrepGateError(
                f"cannot read Semgrep container id file: {exc}"
            ) from exc
        if not re.fullmatch(r"[0-9a-f]{64}", cidfile_id):
            raise SemgrepGateError("Semgrep container id file is malformed")
    inspect_target = cidfile_id or container_name
    try:
        inspection = command_runner(
            ["docker", "inspect", "--format", "{{.Id}} {{.Name}}", inspect_target],
            cwd=scan_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SemgrepGateError(f"Semgrep container inspection failed: {exc}") from exc
    if inspection.returncode != 0:
        detail = (inspection.stderr or inspection.stdout or "").strip()
        if cidfile_id is not None or not re.search(
            r"no such (?:object|container)", detail, re.IGNORECASE
        ):
            suffix = f": {detail}" if detail else ""
            raise SemgrepGateError(
                f"Semgrep container inspection failed ({inspection.returncode}){suffix}"
            )
    else:
        fields = inspection.stdout.strip().split()
        if (
            len(fields) != 2
            or not re.fullmatch(r"[0-9a-f]{64}", fields[0])
            or fields[1] != f"/{container_name}"
            or (cidfile_id is not None and fields[0] != cidfile_id)
        ):
            raise SemgrepGateError("Semgrep container identity does not match this run")
        container_id = fields[0]

    if container_id is not None:
        try:
            cleanup = command_runner(
                ["docker", "rm", "-v", "--force", container_id],
                cwd=scan_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SemgrepGateError(f"Semgrep container cleanup failed: {exc}") from exc
        if cleanup.returncode != 0:
            detail = (cleanup.stderr or cleanup.stdout or "").strip()
            suffix = f": {detail}" if detail else ""
            raise SemgrepGateError(
                f"Semgrep container cleanup failed ({cleanup.returncode}){suffix}"
            )
    elif result is not None and result.returncode in (0, 1):
        raise SemgrepGateError("Semgrep returned a scan status without a container")

    if scan_error is not None:
        raise SemgrepGateError(
            f"Semgrep container could not run: {scan_error}"
        ) from scan_error
    if result is None:
        raise SemgrepGateError("Semgrep container returned no result")
    return result.returncode


def _run_dispositions_gate(
    *,
    snapshot_root: Path,
    results_path: Path,
    command_runner: CommandRunner,
) -> int:
    gate_path = snapshot_root / "scripts" / "quality" / "semgrep_dispositions_gate.py"
    dispositions_path = snapshot_root / "quality" / "semgrep-dispositions.json"
    command = [
        sys.executable,
        "-I",
        str(gate_path),
        str(results_path),
        "--repository-root",
        str(snapshot_root),
        "--dispositions",
        str(dispositions_path),
        "--strip-check-prefix",
        "out.",
    ]
    try:
        result = command_runner(
            command,
            cwd=snapshot_root,
            check=False,
            timeout=SCAN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SemgrepGateError(
            f"Semgrep dispositions gate could not run: {exc}"
        ) from exc
    return result.returncode


def _verify_index_unchanged(
    *,
    repository_root: Path,
    expected_entries: Sequence[IndexEntry],
    command_runner: CommandRunner,
    manifest_directory: Path,
    target_count: int,
    manifest_sha256: str,
) -> None:
    try:
        current_entries = _indexed_manifest(
            repository_root, command_runner=command_runner
        )
    except SemgrepGateError:
        _write_consistency_summary(
            manifest_directory,
            status="unreadable",
            target_count=target_count,
            manifest_sha256=manifest_sha256,
            index_before_sha256=_index_digest(expected_entries),
            index_after_sha256=None,
        )
        raise
    changed_paths = _changed_index_paths(expected_entries, current_entries)
    _write_consistency_summary(
        manifest_directory,
        status="match" if not changed_paths else "mismatch",
        target_count=target_count,
        manifest_sha256=manifest_sha256,
        index_before_sha256=_index_digest(expected_entries),
        index_after_sha256=_index_digest(current_entries),
        changed_paths=changed_paths,
    )
    if changed_paths:
        raise SemgrepGateError(
            "Git index changed during Semgrep scan: " + ", ".join(changed_paths)
        )


def _prepare_output_directory(
    output_directory: Path, repository_root: Path, private_work_root: Path
) -> Path:
    if output_directory.is_symlink() or output_directory.is_junction():
        raise SemgrepGateError("Semgrep report output directory must not be linked")
    destination = output_directory.resolve()
    repository = repository_root.resolve()
    if destination.is_relative_to(repository) and not destination.is_relative_to(
        private_work_root.resolve()
    ):
        raise SemgrepGateError(
            "Semgrep report output must be outside the repository or under its private audit directory"
        )
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for name in (
            "semgrep.json",
            "semgrep.sarif",
            "semgrep-primary.json",
            "semgrep-primary.sarif",
            "semgrep-dockerfile.json",
            "semgrep-dockerfile.sarif",
            "semgrep-dockerfile-raw.json",
            "semgrep-dockerfile-raw.sarif",
            "semgrep-dockerfile-inputs.json",
            "security-rules-dockerfile.json",
            "semgrep-mts.json",
            "semgrep-mts.sarif",
            "semgrep-inline-js.json",
            "semgrep-inline-js.sarif",
            "semgrep-inline-js-raw.json",
            "semgrep-inline-js-raw.sarif",
            "semgrep-inline-js-inputs.json",
            "security-rules-mts.json",
            "semgrep-targets.json",
            "semgrep-targets-consistency.json",
            "semgrep-rendered-target-overlay.json",
        ):
            report_path = destination / name
            if not report_path.exists() and not report_path.is_symlink():
                continue
            if report_path.is_symlink() or report_path.is_junction():
                raise SemgrepGateError(f"Semgrep report path is linked: {name}")
            if not report_path.is_file():
                raise SemgrepGateError(f"Semgrep report path is not a file: {name}")
            report_path.unlink()
    except OSError as exc:
        raise SemgrepGateError(f"cannot prepare Semgrep report output: {exc}") from exc
    return destination


def _persist_reports(output_directory: Path, report_directory: Path | None) -> None:
    if report_directory is None:
        return
    for name in (
        "semgrep.json",
        "semgrep.sarif",
        "semgrep-primary.json",
        "semgrep-primary.sarif",
        "semgrep-dockerfile.json",
        "semgrep-dockerfile.sarif",
        "semgrep-dockerfile-raw.json",
        "semgrep-dockerfile-raw.sarif",
        "semgrep-dockerfile-inputs.json",
        "security-rules-dockerfile.json",
        "semgrep-mts.json",
        "semgrep-mts.sarif",
        "semgrep-inline-js.json",
        "semgrep-inline-js.sarif",
        "semgrep-inline-js-raw.json",
        "semgrep-inline-js-raw.sarif",
        "semgrep-inline-js-inputs.json",
        "security-rules-mts.json",
    ):
        source = output_directory / name
        try:
            if not source.exists() and not source.is_symlink():
                continue
            if source.is_symlink() or source.is_junction() or not source.is_file():
                raise SemgrepGateError(f"Semgrep report is not a regular file: {name}")
            if source.stat().st_size > 0:
                shutil.copyfile(source, report_directory / name)
        except OSError as exc:
            raise SemgrepGateError(
                f"cannot preserve Semgrep report {name}: {exc}"
            ) from exc


def _preserve_primary_scan_reports(output_directory: Path) -> None:
    for extension in ("json", "sarif"):
        source = output_directory / f"semgrep.{extension}"
        destination = output_directory / f"semgrep-primary.{extension}"
        if (
            source.is_symlink()
            or source.is_junction()
            or not source.is_file()
            or destination.exists()
            or destination.is_symlink()
            or destination.is_junction()
        ):
            raise SemgrepGateError("primary Semgrep evidence is missing or not fresh")
        try:
            shutil.copyfile(source, destination)
        except OSError as exc:
            raise SemgrepGateError(
                f"cannot preserve primary Semgrep evidence: {extension}"
            ) from exc


@dataclass(frozen=True)
class _SupplementContext:
    """Immutable inputs shared by the independent Semgrep supplement phases."""

    image: str
    repository_root: Path
    run_command: CommandRunner
    temporary_root: Path
    scan_output_directory: Path
    scan_root: Path
    snapshot_manifest: list[dict[str, str]]
    index_entries: list[IndexEntry]
    manifest_directory: Path
    manifest_sha256: str
    overlay_root: Path
    overlay_target_hashes: dict[str, str]
    ignore_matcher: Callable[[str], bool] | None
    report_directory: Path | None
    results_path: Path
    sarif_path: Path


def _run_dockerfile_supplement(context: _SupplementContext) -> bool:
    """Run and merge the reviewed Dockerfile-only supplemental scan."""
    image = context.image
    repository_root = context.repository_root
    run_command = context.run_command
    temporary_root = context.temporary_root
    scan_output_directory = context.scan_output_directory
    scan_root = context.scan_root
    snapshot_manifest = context.snapshot_manifest
    index_entries = context.index_entries
    manifest_directory = context.manifest_directory
    manifest_sha256 = context.manifest_sha256
    overlay_root = context.overlay_root
    overlay_target_hashes = context.overlay_target_hashes
    ignore_matcher = context.ignore_matcher
    report_directory = context.report_directory
    results_path = context.results_path
    sarif_path = context.sarif_path
    primary_reports_preserved = False
    dockerfile_targets = _dockerfile_scan_targets(
        overlay_root, overlay_target_hashes, ignore_matcher
    )
    if dockerfile_targets:
        primary_report = _read_semgrep_report(results_path)
        primary_paths = primary_report.get("paths")
        primary_scanned = (
            primary_paths.get("scanned") if isinstance(primary_paths, dict) else None
        )
        if not isinstance(primary_scanned, list):
            raise SemgrepGateError(
                "primary Semgrep report has malformed scanned target evidence"
            )
        normalized_primary = {_normalize_report_path(path) for path in primary_scanned}
        if normalized_primary.intersection(dockerfile_targets):
            raise SemgrepGateError(
                "primary Semgrep scan already covered a Dockerfile target"
            )
        _preserve_primary_scan_reports(scan_output_directory)
        primary_reports_preserved = True
        dockerfile_config_path = (
            scan_output_directory / "security-rules-dockerfile.json"
        )
        dockerfile_config_sha256, dockerfile_rule_ids = _write_dockerfile_rules_config(
            scan_output_directory / "security-rules.json",
            dockerfile_config_path,
        )
        dockerfile_scan_root = temporary_root / "dockerfile-inputs"
        dockerfile_aliases, alias_to_source, source_mapping_sha256 = (
            _materialize_dockerfile_scan_inputs(
                source_root=overlay_root,
                destination=dockerfile_scan_root,
                targets=dockerfile_targets,
                source_manifest=snapshot_manifest,
                overlay_target_hashes=overlay_target_hashes,
                mapping_manifest_path=(
                    scan_output_directory / "semgrep-dockerfile-inputs.json"
                ),
            )
        )
        dockerfile_input_hashes = _tree_file_hashes(
            dockerfile_scan_root,
            description="Dockerfile parser alias projection",
        )

        dockerfile_scan_status: int | None = None
        dockerfile_scan_error: SemgrepGateError | None = None
        try:
            dockerfile_scan_status = _docker_scan(
                scan_root=dockerfile_scan_root,
                output_directory=scan_output_directory,
                image=image,
                command_runner=run_command,
                scan_id="semgrep-dockerfile",
                config_name="security-rules-dockerfile.json",
                report_prefix="semgrep-dockerfile-raw",
                target_paths=dockerfile_aliases,
                scan_dockerfile_aliases=True,
                timeout_seconds=DOCKERFILE_SCAN_TIMEOUT_SECONDS,
            )
        except SemgrepGateError as exc:
            dockerfile_scan_error = exc
        _persist_reports(scan_output_directory, report_directory)
        _verify_source_snapshot(scan_root, snapshot_manifest)
        actual_overlay_hashes = _tree_file_hashes(
            overlay_root,
            description="rendered scan overlay after Dockerfile Semgrep",
        )
        if actual_overlay_hashes != overlay_target_hashes:
            dockerfile_scan_error = dockerfile_scan_error or SemgrepGateError(
                "rendered scan overlay changed during Dockerfile Semgrep"
            )
        actual_dockerfile_input_hashes = _tree_file_hashes(
            dockerfile_scan_root,
            description="Dockerfile parser alias projection after Semgrep",
        )
        if actual_dockerfile_input_hashes != dockerfile_input_hashes:
            dockerfile_scan_error = dockerfile_scan_error or SemgrepGateError(
                "Dockerfile parser aliases changed during Semgrep"
            )
        _verify_index_unchanged(
            repository_root=repository_root,
            expected_entries=index_entries,
            command_runner=run_command,
            manifest_directory=manifest_directory,
            target_count=len(snapshot_manifest),
            manifest_sha256=manifest_sha256,
        )
        if dockerfile_scan_error is not None:
            raise dockerfile_scan_error
        if dockerfile_scan_status not in (0, 1):
            raise SemgrepGateError(
                "Dockerfile supplemental Semgrep scan returned an invalid status"
            )

        dockerfile_raw_json_path = scan_output_directory / "semgrep-dockerfile-raw.json"
        dockerfile_raw_sarif_path = (
            scan_output_directory / "semgrep-dockerfile-raw.sarif"
        )
        for evidence_path in (
            dockerfile_raw_json_path,
            dockerfile_raw_sarif_path,
        ):
            if (
                not evidence_path.is_file()
                or evidence_path.is_symlink()
                or evidence_path.is_junction()
                or evidence_path.stat().st_size == 0
            ):
                raise SemgrepGateError(
                    "Dockerfile supplemental Semgrep evidence is missing or invalid"
                )
        dockerfile_raw_report = _read_semgrep_report(dockerfile_raw_json_path)
        _validate_dockerfile_supplement_report(
            dockerfile_raw_report, dockerfile_aliases, alias_to_source
        )
        dockerfile_report = _remap_dockerfile_report_paths(
            dockerfile_raw_report, alias_to_source
        )
        dockerfile_json_path = scan_output_directory / "semgrep-dockerfile.json"
        _write_new_json_report(dockerfile_json_path, dockerfile_report)
        dockerfile_raw_sarif = _read_semgrep_report(dockerfile_raw_sarif_path)
        dockerfile_sarif = _remap_dockerfile_sarif(
            dockerfile_raw_sarif, alias_to_source
        )
        dockerfile_sarif_path = scan_output_directory / "semgrep-dockerfile.sarif"
        _write_new_json_report(dockerfile_sarif_path, dockerfile_sarif)
        primary_sarif = _read_semgrep_report(sarif_path)
        _write_semgrep_json(
            results_path,
            _merge_semgrep_reports(
                primary_report,
                dockerfile_report,
                targets=dockerfile_targets,
                javascript_typescript_config_sha256=dockerfile_config_sha256,
                javascript_typescript_rule_ids=dockerfile_rule_ids,
                supplemental_evidence={
                    "mode": "canonical-dockerfile-alias",
                    "targets": list(dockerfile_targets),
                    "aliases": alias_to_source,
                    "source_mapping_manifest_sha256": source_mapping_sha256,
                    "dockerfile_config_sha256": dockerfile_config_sha256,
                    "dockerfile_rule_ids": list(dockerfile_rule_ids),
                    "time": dockerfile_report.get("time"),
                },
            ),
        )
        _write_semgrep_sarif(
            sarif_path,
            _merge_sarif_reports(primary_sarif, dockerfile_sarif),
        )
        _persist_reports(scan_output_directory, report_directory)
    return primary_reports_preserved


def _run_mts_supplement(
    context: _SupplementContext, *, primary_reports_preserved: bool
) -> bool:
    """Run and merge the reviewed MTS supplemental scan."""
    image = context.image
    repository_root = context.repository_root
    run_command = context.run_command
    scan_output_directory = context.scan_output_directory
    scan_root = context.scan_root
    snapshot_manifest = context.snapshot_manifest
    index_entries = context.index_entries
    manifest_directory = context.manifest_directory
    manifest_sha256 = context.manifest_sha256
    overlay_root = context.overlay_root
    overlay_target_hashes = context.overlay_target_hashes
    ignore_matcher = context.ignore_matcher
    report_directory = context.report_directory
    results_path = context.results_path
    sarif_path = context.sarif_path
    mts_targets = _mts_scan_targets(overlay_root, overlay_target_hashes, ignore_matcher)
    if mts_targets:
        primary_report = _read_semgrep_report(results_path)
        primary_paths = primary_report.get("paths")
        primary_scanned = (
            primary_paths.get("scanned") if isinstance(primary_paths, dict) else None
        )
        if not isinstance(primary_scanned, list):
            raise SemgrepGateError(
                "primary Semgrep report has malformed scanned target evidence"
            )
        normalized_primary = {_normalize_report_path(path) for path in primary_scanned}
        if normalized_primary.intersection(mts_targets):
            raise SemgrepGateError(
                "primary Semgrep scan already covered an MTS supplemental target"
            )
        if not primary_reports_preserved:
            _preserve_primary_scan_reports(scan_output_directory)
        typescript_config_path = scan_output_directory / "security-rules-mts.json"
        javascript_typescript_config_sha256, javascript_typescript_rule_ids = (
            _write_mts_rules_config(
                scan_output_directory / "security-rules.json",
                typescript_config_path,
            )
        )

        mts_scan_status: int | None = None
        mts_scan_error: SemgrepGateError | None = None
        try:
            mts_scan_status = _docker_scan(
                scan_root=overlay_root,
                output_directory=scan_output_directory,
                image=image,
                command_runner=run_command,
                scan_id="semgrep-mts",
                config_name="security-rules-mts.json",
                report_prefix="semgrep-mts",
                target_paths=mts_targets,
                scan_unknown_extensions=True,
            )
        except SemgrepGateError as exc:
            mts_scan_error = exc
        _persist_reports(scan_output_directory, report_directory)
        _verify_source_snapshot(scan_root, snapshot_manifest)
        actual_overlay_hashes = _tree_file_hashes(
            overlay_root, description="rendered scan overlay after MTS Semgrep"
        )
        if actual_overlay_hashes != overlay_target_hashes:
            mts_scan_error = mts_scan_error or SemgrepGateError(
                "rendered scan overlay changed during MTS Semgrep"
            )
        _verify_index_unchanged(
            repository_root=repository_root,
            expected_entries=index_entries,
            command_runner=run_command,
            manifest_directory=manifest_directory,
            target_count=len(snapshot_manifest),
            manifest_sha256=manifest_sha256,
        )
        if mts_scan_error is not None:
            raise mts_scan_error
        if mts_scan_status is None or mts_scan_status not in (0, 1):
            raise SemgrepGateError(
                "MTS supplemental Semgrep scan returned an invalid status"
            )

        mts_json_path = scan_output_directory / "semgrep-mts.json"
        mts_sarif_path = scan_output_directory / "semgrep-mts.sarif"
        for evidence_path in (mts_json_path, mts_sarif_path):
            if (
                not evidence_path.is_file()
                or evidence_path.is_symlink()
                or evidence_path.is_junction()
                or evidence_path.stat().st_size == 0
            ):
                raise SemgrepGateError(
                    "MTS supplemental Semgrep evidence is missing or invalid"
                )
        mts_report = _read_semgrep_report(mts_json_path)
        _validate_mts_supplement_report(mts_report, mts_targets)
        mts_sarif = _read_semgrep_report(mts_sarif_path)
        primary_sarif = _read_semgrep_report(sarif_path)
        _write_semgrep_json(
            results_path,
            _merge_semgrep_reports(
                primary_report,
                mts_report,
                targets=mts_targets,
                javascript_typescript_config_sha256=javascript_typescript_config_sha256,
                javascript_typescript_rule_ids=javascript_typescript_rule_ids,
            ),
        )
        _write_semgrep_sarif(sarif_path, _merge_sarif_reports(primary_sarif, mts_sarif))
        _persist_reports(scan_output_directory, report_directory)
    return primary_reports_preserved


def _run_inline_javascript_supplement(
    context: _SupplementContext, *, primary_reports_preserved: bool
) -> bool:
    """Run and merge the reviewed inline JavaScript supplemental scan."""
    image = context.image
    repository_root = context.repository_root
    run_command = context.run_command
    temporary_root = context.temporary_root
    scan_output_directory = context.scan_output_directory
    scan_root = context.scan_root
    snapshot_manifest = context.snapshot_manifest
    index_entries = context.index_entries
    manifest_directory = context.manifest_directory
    manifest_sha256 = context.manifest_sha256
    overlay_root = context.overlay_root
    overlay_target_hashes = context.overlay_target_hashes
    ignore_matcher = context.ignore_matcher
    report_directory = context.report_directory
    results_path = context.results_path
    sarif_path = context.sarif_path
    inline_javascript_targets = _inline_javascript_scan_targets(
        overlay_root,
        overlay_target_hashes,
        snapshot_manifest,
        ignore_matcher,
    )
    if inline_javascript_targets:
        primary_report = _read_semgrep_report(results_path)
        primary_paths = primary_report.get("paths")
        primary_scanned = (
            primary_paths.get("scanned") if isinstance(primary_paths, dict) else None
        )
        if not isinstance(primary_scanned, list):
            raise SemgrepGateError(
                "primary Semgrep report has malformed scanned target evidence"
            )
        inline_source_paths = {source.path for source in inline_javascript_targets}
        normalized_primary = {_normalize_report_path(path) for path in primary_scanned}
        _validate_inline_external_source_coverage(
            inline_javascript_targets, primary_scanned
        )
        if normalized_primary.intersection(inline_source_paths):
            raise SemgrepGateError(
                "primary Semgrep scan already covered an inline JavaScript source"
            )
        if not primary_reports_preserved:
            _preserve_primary_scan_reports(scan_output_directory)
            primary_reports_preserved = True

        javascript_config_path = scan_output_directory / "security-rules-mts.json"
        (
            javascript_typescript_config_sha256,
            javascript_typescript_rule_ids,
        ) = _ensure_mts_rules_config(
            scan_output_directory / "security-rules.json",
            javascript_config_path,
        )
        javascript_rule_ids = _javascript_rule_ids(javascript_config_path)
        inline_scan_root = temporary_root / "inline-javascript-inputs"
        (
            inline_aliases,
            inline_bindings,
            inline_source_mapping_sha256,
        ) = _materialize_inline_javascript_inputs(
            source_root=overlay_root,
            destination=inline_scan_root,
            targets=inline_javascript_targets,
            source_manifest=snapshot_manifest,
            overlay_target_hashes=overlay_target_hashes,
            mapping_manifest_path=(
                scan_output_directory / "semgrep-inline-js-inputs.json"
            ),
            source_snapshot_manifest_sha256=manifest_sha256,
            ignore_matcher=ignore_matcher,
        )
        inline_mapping_manifest_path = (
            scan_output_directory / "semgrep-inline-js-inputs.json"
        )
        _verify_inline_javascript_inputs(
            source_root=overlay_root,
            destination=inline_scan_root,
            targets=inline_javascript_targets,
            source_manifest=snapshot_manifest,
            overlay_target_hashes=overlay_target_hashes,
            source_snapshot_manifest_sha256=manifest_sha256,
            mapping_manifest_path=inline_mapping_manifest_path,
            expected_mapping_manifest_sha256=inline_source_mapping_sha256,
            ignore_matcher=ignore_matcher,
        )
        inline_input_hashes = _tree_file_hashes(
            inline_scan_root,
            description="inline JavaScript parser alias projection",
        )
        inline_scan_status: int | None = None
        inline_scan_error: SemgrepGateError | None = None
        try:
            inline_scan_status = _docker_scan(
                scan_root=inline_scan_root,
                output_directory=scan_output_directory,
                image=image,
                command_runner=run_command,
                scan_id="semgrep-inline-js",
                config_name="security-rules-mts.json",
                report_prefix="semgrep-inline-js-raw",
                target_paths=inline_aliases,
                scan_inline_javascript_aliases=True,
                timeout_seconds=INLINE_JAVASCRIPT_SCAN_TIMEOUT_SECONDS,
            )
        except SemgrepGateError as exc:
            inline_scan_error = exc
        _persist_reports(scan_output_directory, report_directory)
        _verify_source_snapshot(scan_root, snapshot_manifest)
        actual_overlay_hashes = _tree_file_hashes(
            overlay_root,
            description="rendered scan overlay after inline JavaScript Semgrep",
        )
        if actual_overlay_hashes != overlay_target_hashes:
            inline_scan_error = inline_scan_error or SemgrepGateError(
                "rendered scan overlay changed during inline JavaScript Semgrep"
            )
        try:
            _verify_inline_javascript_inputs(
                source_root=overlay_root,
                destination=inline_scan_root,
                targets=inline_javascript_targets,
                source_manifest=snapshot_manifest,
                overlay_target_hashes=overlay_target_hashes,
                source_snapshot_manifest_sha256=manifest_sha256,
                mapping_manifest_path=inline_mapping_manifest_path,
                expected_mapping_manifest_sha256=inline_source_mapping_sha256,
                ignore_matcher=ignore_matcher,
            )
        except SemgrepGateError as exc:
            inline_scan_error = inline_scan_error or exc
        actual_inline_input_hashes = _tree_file_hashes(
            inline_scan_root,
            description="inline JavaScript parser aliases after Semgrep",
        )
        if actual_inline_input_hashes != inline_input_hashes:
            inline_scan_error = inline_scan_error or SemgrepGateError(
                "inline JavaScript parser aliases changed during Semgrep"
            )
        _verify_index_unchanged(
            repository_root=repository_root,
            expected_entries=index_entries,
            command_runner=run_command,
            manifest_directory=manifest_directory,
            target_count=len(snapshot_manifest),
            manifest_sha256=manifest_sha256,
        )
        if inline_scan_error is not None:
            raise inline_scan_error
        if inline_scan_status not in (0, 1):
            raise SemgrepGateError(
                "inline JavaScript supplemental Semgrep scan returned an invalid status"
            )

        inline_raw_json_path = scan_output_directory / "semgrep-inline-js-raw.json"
        inline_raw_sarif_path = scan_output_directory / "semgrep-inline-js-raw.sarif"
        for evidence_path in (inline_raw_json_path, inline_raw_sarif_path):
            if (
                not evidence_path.is_file()
                or evidence_path.is_symlink()
                or evidence_path.is_junction()
                or evidence_path.stat().st_size == 0
            ):
                raise SemgrepGateError(
                    "inline JavaScript Semgrep evidence is missing or invalid"
                )
        inline_raw_report = _read_semgrep_report(inline_raw_json_path)
        _validate_inline_javascript_supplement_report(
            inline_raw_report,
            inline_aliases,
            inline_bindings,
            javascript_rule_ids,
        )
        inline_report = _remap_inline_javascript_report(
            inline_raw_report, inline_bindings
        )
        inline_json_path = scan_output_directory / "semgrep-inline-js.json"
        _write_new_json_report(inline_json_path, inline_report)
        inline_raw_sarif = _read_semgrep_report(inline_raw_sarif_path)
        inline_sarif = _remap_inline_javascript_sarif(
            inline_raw_sarif,
            inline_bindings,
            javascript_typescript_rule_ids,
            javascript_rule_ids,
        )
        inline_sarif_path = scan_output_directory / "semgrep-inline-js.sarif"
        _write_new_json_report(inline_sarif_path, inline_sarif)
        primary_sarif = _read_semgrep_report(sarif_path)
        _write_semgrep_json(
            results_path,
            _merge_semgrep_reports(
                primary_report,
                inline_report,
                targets=tuple(source.path for source in inline_javascript_targets),
                javascript_typescript_config_sha256=javascript_typescript_config_sha256,
                javascript_typescript_rule_ids=javascript_typescript_rule_ids,
                supplemental_evidence={
                    "mode": "inline-javascript-source-slice",
                    "targets": [source.path for source in inline_javascript_targets],
                    "aliases": {
                        alias: binding.path
                        for alias, binding in inline_bindings.items()
                    },
                    "source_snapshot_manifest_sha256": manifest_sha256,
                    "source_mapping_manifest_sha256": inline_source_mapping_sha256,
                    "javascript_typescript_config_sha256": javascript_typescript_config_sha256,
                    "javascript_typescript_rule_ids": list(
                        javascript_typescript_rule_ids
                    ),
                    "javascript_rule_ids": list(javascript_rule_ids),
                    "time": inline_report.get("time"),
                },
            ),
        )
        _write_semgrep_sarif(
            sarif_path,
            _merge_sarif_reports(primary_sarif, inline_sarif),
        )
        _persist_reports(scan_output_directory, report_directory)
    return primary_reports_preserved


def _evaluate_merged_dispositions(context: _SupplementContext) -> int:
    """Evaluate the merged report and verify the unchanged source snapshots."""
    repository_root = context.repository_root
    run_command = context.run_command
    scan_root = context.scan_root
    snapshot_manifest = context.snapshot_manifest
    index_entries = context.index_entries
    manifest_directory = context.manifest_directory
    manifest_sha256 = context.manifest_sha256
    overlay_root = context.overlay_root
    overlay_target_hashes = context.overlay_target_hashes
    results_path = context.results_path
    gate_status: int | None = None
    gate_error: SemgrepGateError | None = None
    try:
        gate_status = _run_dispositions_gate(
            snapshot_root=overlay_root,
            results_path=results_path,
            command_runner=run_command,
        )
    except SemgrepGateError as exc:
        gate_error = exc
    _verify_source_snapshot(scan_root, snapshot_manifest)
    actual_overlay_hashes = _tree_file_hashes(
        overlay_root, description="rendered scan overlay after disposition gate"
    )
    if actual_overlay_hashes != overlay_target_hashes:
        raise SemgrepGateError(
            "rendered scan overlay changed during disposition evaluation"
        )
    _verify_index_unchanged(
        repository_root=repository_root,
        expected_entries=index_entries,
        command_runner=run_command,
        manifest_directory=manifest_directory,
        target_count=len(snapshot_manifest),
        manifest_sha256=manifest_sha256,
    )
    if gate_error is not None:
        raise gate_error
    if gate_status is None:
        raise SemgrepGateError("Semgrep dispositions gate returned no status")
    if gate_status != 0:
        return 1
    return gate_status


def run_gate(
    image: str,
    repository_root: Path = REPOSITORY_ROOT,
    *,
    command_runner: CommandRunner | None = None,
    temporary_parent: Path | None = None,
    output_directory: Path | None = None,
    helm_archive_path: Path | None = None,
) -> int:
    """Run the same pinned selector, Semgrep command and disposition gate as CI."""

    if not IMAGE_PATTERN.fullmatch(image):
        raise SemgrepGateError(
            "Semgrep image must have a version tag and immutable digest"
        )
    if not repository_root.is_dir():
        raise SemgrepGateError(f"repository root does not exist: {repository_root}")
    run_command = command_runner or subprocess.run
    _validate_semgrep_ignore_policy(repository_root)
    if temporary_parent is None:
        common_dir = _git_common_directory(repository_root, command_runner=run_command)
        private_work_root = common_dir / "ue-audit-work"
        temporary_parent = private_work_root / "semgrep"
    else:
        private_work_root = Path(REPOSITORY_ROOT) / ".git" / "ue-audit-work"
        try:
            if not temporary_parent.resolve().is_relative_to(
                private_work_root.resolve()
            ):
                raise SemgrepGateError(
                    "Semgrep temporary workspace must be under the private Git audit directory"
                )
        except OSError as exc:
            raise SemgrepGateError(
                f"Semgrep temporary workspace is unavailable: {exc}"
            ) from exc
    try:
        temporary_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SemgrepGateError(
            f"cannot create Semgrep private workspace: {exc}"
        ) from exc
    report_directory = (
        _prepare_output_directory(output_directory, repository_root, private_work_root)
        if output_directory is not None
        else None
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix="ue-semgrep-", dir=temporary_parent
        ) as temporary_name:
            temporary_root = Path(temporary_name)
            scan_output_directory = temporary_root / "out"
            scan_output_directory.mkdir()
            scan_root, snapshot_manifest, index_entries = _create_scan_snapshot(
                repository_root,
                temporary_root / "src",
                command_runner=run_command,
            )
            _verify_source_snapshot(scan_root, snapshot_manifest)
            _validate_semgrep_ignore_policy(scan_root)
            staged_image = _precommit_semgrep_image(scan_root)
            if staged_image != image:
                raise SemgrepGateError(
                    "requested Semgrep image does not match the staged pre-commit hook"
                )
            rules_commit = _workflow_rules_commit(scan_root)
            rules_root = _checkout_rules(
                rules_commit,
                temporary_root / "rules",
                command_runner=run_command,
            )
            manifest_directory = report_directory or scan_output_directory
            manifest_sha256 = _write_snapshot_manifest(
                snapshot_manifest, manifest_directory
            )
            overlay_destination = temporary_root / "scan"
            _chart_template_sources(scan_root)
            overlay_module = _load_overlay_helper(scan_root)
            try:
                archive_pin = _validated_helm_archive_pin(
                    overlay_module.helm_archive_pin(scan_root, snapshot_manifest)
                )
            except overlay_module.HelmOverlayError as exc:
                raise SemgrepGateError(f"Helm archive policy rejected: {exc}") from exc
            except SemgrepGateError:
                raise
            except Exception as exc:
                raise SemgrepGateError(
                    f"Helm archive policy could not be verified: {exc}"
                ) from exc
            if helm_archive_path is None:
                archive_path = _download_helm_archive(
                    archive_pin, temporary_root / "helm.archive"
                )
            else:
                archive_path = _validate_prefetched_helm_archive(
                    helm_archive_path,
                    pin=archive_pin,
                    source_root=scan_root,
                )
            try:
                helm_tool = overlay_module.verify_helm_archive(
                    scan_root,
                    snapshot_manifest,
                    archive_path,
                    temporary_root / "helm-tool",
                )
                overlay_root, overlay_provenance = overlay_module.prepare_overlay(
                    scan_root,
                    overlay_destination,
                    snapshot_manifest,
                    helm_tool=helm_tool,
                    bounded_runner=overlay_module.bounded_process_runner,
                )
            except overlay_module.HelmOverlayError as exc:
                raise SemgrepGateError(
                    f"Helm rendered-target preparation failed: {exc}"
                ) from exc
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SemgrepGateError(
                    f"Helm rendered-target preparation failed: {exc}"
                ) from exc
            except Exception as exc:
                raise SemgrepGateError(
                    f"Helm rendered-target preparation failed: {exc}"
                ) from exc
            if not isinstance(overlay_root, Path):
                raise SemgrepGateError("Helm helper returned an invalid overlay root")
            try:
                resolved_overlay = overlay_root.resolve(strict=True)
                resolved_expected = overlay_destination.resolve(strict=True)
                resolved_overlay.relative_to(temporary_root.resolve(strict=True))
            except (OSError, ValueError) as exc:
                raise SemgrepGateError(
                    "Helm helper returned an overlay outside the private workspace"
                ) from exc
            if (
                resolved_overlay != resolved_expected
                or overlay_root.is_symlink()
                or overlay_root.is_junction()
            ):
                raise SemgrepGateError(
                    "Helm helper returned an unexpected or linked overlay root"
                )
            _verify_source_snapshot(scan_root, snapshot_manifest)
            overlay_target_hashes = _validate_overlay_provenance(
                source_root=scan_root,
                overlay_root=overlay_root,
                source_manifest=snapshot_manifest,
                source_manifest_sha256=manifest_sha256,
                provenance=overlay_provenance,
                archive_pin=archive_pin,
                helm_tool=helm_tool,
            )
            ignore_matcher = _validate_semgrep_ignore_policy(overlay_root)
            if not isinstance(overlay_provenance, dict):
                raise SemgrepGateError("Helm helper returned malformed provenance")
            _write_overlay_manifest(overlay_provenance, manifest_directory)
            selector_path = (
                scan_root / "scripts" / "quality" / "select_semgrep_rules.py"
            )
            selector_command = [
                sys.executable,
                "-I",
                str(selector_path),
                "--rules-root",
                str(rules_root),
                "--output",
                str(scan_output_directory / "security-rules.json"),
            ]
            try:
                selection = run_command(
                    selector_command,
                    cwd=scan_root,
                    check=False,
                    timeout=GIT_TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SemgrepGateError(
                    f"Semgrep rule selector could not run: {exc}"
                ) from exc
            if selection.returncode != 0:
                raise SemgrepGateError("Semgrep rule selector failed")

            scan_status: int | None = None
            scan_error: SemgrepGateError | None = None
            try:
                scan_status = _docker_scan(
                    scan_root=overlay_root,
                    output_directory=scan_output_directory,
                    image=image,
                    command_runner=run_command,
                )
            except SemgrepGateError as exc:
                scan_error = exc
            _persist_reports(scan_output_directory, report_directory)
            _verify_source_snapshot(scan_root, snapshot_manifest)
            actual_overlay_hashes = _tree_file_hashes(
                overlay_root, description="rendered scan overlay after Semgrep"
            )
            if actual_overlay_hashes != overlay_target_hashes:
                scan_error = scan_error or SemgrepGateError(
                    "rendered scan overlay changed during Semgrep"
                )
            _verify_index_unchanged(
                repository_root=repository_root,
                expected_entries=index_entries,
                command_runner=run_command,
                manifest_directory=manifest_directory,
                target_count=len(snapshot_manifest),
                manifest_sha256=manifest_sha256,
            )
            if scan_error is not None:
                raise scan_error
            if scan_status is None:
                raise SemgrepGateError("Semgrep scanner returned no status")
            if scan_status not in (0, 1):
                raise SemgrepGateError(
                    f"Semgrep scanner failed with status {scan_status}"
                )
            results_path = scan_output_directory / "semgrep.json"
            sarif_path = scan_output_directory / "semgrep.sarif"
            for evidence_path in (results_path, sarif_path):
                if not evidence_path.is_file() or evidence_path.stat().st_size == 0:
                    raise SemgrepGateError(
                        f"Semgrep did not produce required evidence: {evidence_path.name}"
                    )

            supplement_context = _SupplementContext(
                image=image,
                repository_root=repository_root,
                run_command=run_command,
                temporary_root=temporary_root,
                scan_output_directory=scan_output_directory,
                scan_root=scan_root,
                snapshot_manifest=snapshot_manifest,
                index_entries=index_entries,
                manifest_directory=manifest_directory,
                manifest_sha256=manifest_sha256,
                overlay_root=overlay_root,
                overlay_target_hashes=overlay_target_hashes,
                ignore_matcher=ignore_matcher,
                report_directory=report_directory,
                results_path=results_path,
                sarif_path=sarif_path,
            )
            primary_reports_preserved = _run_dockerfile_supplement(supplement_context)
            primary_reports_preserved = _run_mts_supplement(
                supplement_context,
                primary_reports_preserved=primary_reports_preserved,
            )
            primary_reports_preserved = _run_inline_javascript_supplement(
                supplement_context,
                primary_reports_preserved=primary_reports_preserved,
            )
            if _evaluate_merged_dispositions(supplement_context) != 0:
                return 1
    except OSError as exc:
        raise SemgrepGateError(f"Semgrep temporary workspace failed: {exc}") from exc
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    command_runner: CommandRunner | None = None,
    temporary_parent: Path | None = None,
    output_directory: Path | None = None,
    helm_archive_path: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", help="versioned, digest-pinned Semgrep image")
    parser.add_argument(
        "--output-directory",
        type=Path,
        help="preserve Semgrep JSON and SARIF reports in this directory",
    )
    parser.add_argument(
        "--helm-archive",
        type=Path,
        help="use a prefetched Helm archive after verifying its pinned SHA-256",
    )
    args = parser.parse_args(argv)
    try:
        return run_gate(
            args.image,
            repository_root,
            command_runner=command_runner,
            temporary_parent=temporary_parent,
            output_directory=output_directory or args.output_directory,
            helm_archive_path=helm_archive_path or args.helm_archive,
        )
    except SemgrepGateError as exc:
        print(f"::error::Semgrep gate: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
