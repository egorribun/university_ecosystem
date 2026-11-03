"""AUD-423: operator and security documents agree with the code and with each other.

Each claim below is read from the document and compared with the value the code
defines (AST constants or runtime ``Settings`` defaults), or with the matching claim
in the paired document. A stale default, port or repository path in README,
README.ru, SECURITY, DEPLOY or AGENTS therefore fails this module instead of
surviving until a reviewer spots it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
_PATH_EXTENSIONS = (
    ".py",
    ".md",
    ".go",
    ".yml",
    ".yaml",
    ".json",
    ".ts",
    ".tsx",
    ".mjs",
    ".sh",
    ".ps1",
    ".sql",
    ".toml",
    ".conf",
    ".rs",
)
_ACCESS_POINT_HEADINGS = ("### 🌐 Access Points", "### 🌐 Точки доступа")
_DOCS_WITH_PATHS = (
    "README.md",
    "README.ru.md",
    "SECURITY.md",
    "AGENTS.md",
    "CONFIGURATION.md",
    "docs/DEPLOY.md",
    "docs/DEPLOY.en.md",
)


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _module_constants(relative: str) -> dict[str, object]:
    tree = ast.parse(_text(relative), filename=relative)
    constants: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value
    return constants


def _access_point_block(relative: str, heading: str) -> str:
    lines = _text(relative).splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(heading))
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        block.append(line)
    return "\n".join(block)


def _access_point_endpoints(relative: str, heading: str) -> list[str]:
    block = _access_point_block(relative, heading)
    return sorted(re.findall(r"localhost(?::\d+)?(?:/[^\s)\]`]*)?", block))


def test_security_argon2_parameters_match_the_hasher_constants() -> None:
    constants = _module_constants("app/auth/security.py")
    claimed = re.search(
        r"time cost (\d+), memory (\d+) MiB, parallelism (\d+)", _text("SECURITY.md")
    )

    assert claimed is not None
    assert int(claimed.group(1)) == constants["ARGON2_TIME_COST"]
    assert int(claimed.group(2)) * 1024 == constants["ARGON2_MEMORY_COST_KIB"]
    assert int(claimed.group(3)) == constants["ARGON2_PARALLELISM"]


def test_deploy_guides_state_the_runtime_defaults_of_scanner_and_metrics_settings() -> (
    None
):
    defaults = Settings.model_fields
    expected = {
        "EVENT_FILE_SCANNER_HOST": defaults["event_file_scanner_host"].default,
        "EVENT_FILE_SCANNER_PORT": defaults["event_file_scanner_port"].default,
        "NOTIFICATIONS_WORKER_METRICS_HOST": defaults[
            "notifications_worker_metrics_host"
        ].default,
        "NOTIFICATIONS_WORKER_METRICS_PORT": defaults[
            "notifications_worker_metrics_port"
        ].default,
    }
    scanner_claim = (
        f"`{expected['EVENT_FILE_SCANNER_HOST']}:{expected['EVENT_FILE_SCANNER_PORT']}`"
    )
    metrics_claim = (
        f"`{expected['NOTIFICATIONS_WORKER_METRICS_HOST']}:"
        f"{expected['NOTIFICATIONS_WORKER_METRICS_PORT']}`"
    )

    for relative in ("docs/DEPLOY.md", "docs/DEPLOY.en.md"):
        document = _text(relative)
        assert scanner_claim in document, relative
        assert metrics_claim in document, relative


def test_access_point_endpoints_match_between_the_english_and_russian_readmes() -> None:
    english = _access_point_endpoints("README.md", _ACCESS_POINT_HEADINGS[0])
    russian = _access_point_endpoints("README.ru.md", _ACCESS_POINT_HEADINGS[1])

    assert english
    assert english == russian


def _repository_path_tokens(document: str) -> set[str]:
    tokens: set[str] = set()
    for match in re.finditer(r"`([^`\s]+)`", document):
        tokens.add(match.group(1))
    for match in re.finditer(r"\]\((?!https?://|mailto:|#)([^)\s]+)\)", document):
        tokens.add(match.group(1))
    paths = set()
    for token in tokens:
        candidate = token.rsplit("=", 1)[-1].split("#", 1)[0]
        if "/" not in candidate or not candidate.endswith(_PATH_EXTENSIONS):
            continue
        if any(marker in candidate for marker in ("*", "{", "<", "$", "://")):
            continue
        paths.add(candidate)
    return paths


def test_repository_paths_named_in_cross_document_guides_exist() -> None:
    missing: list[str] = []
    for relative in _DOCS_WITH_PATHS:
        document_dir = (ROOT / relative).parent
        for candidate in sorted(_repository_path_tokens(_text(relative))):
            # DEPLOY guides name frontend paths relative to the frontend directory.
            bases = (ROOT, document_dir, ROOT / "frontend")
            if not any(
                (base / candidate.removeprefix("./")).exists() for base in bases
            ):
                missing.append(f"{relative}: {candidate}")

    assert missing == []


def test_path_census_detects_a_stale_repository_path() -> None:
    stale = "Run `scripts/does_not_exist.py` before the release."

    assert _repository_path_tokens(stale) == {"scripts/does_not_exist.py"}
