"""Keep every relative link in the authored Markdown documentation resolvable.

The unit tests pin the behaviour of ``scripts/docs/check_markdown_links.py``;
the repository contract runs it over every tracked ``*.md`` file outside the
vendored agent skill catalogs, including heading anchors.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs.check_markdown_links import (
    find_missing,
    github_slug,
    heading_anchors,
    tracked_markdown,
    tracked_targets,
)

ROOT = Path(__file__).resolve().parents[1]

# Links that were already broken when the dated audit evidence was recorded
# (session-memory or machine-local paths, and wave-local design notes, scripts
# and tests deleted after the wave). The reports are never rewritten, so the
# links stay verbatim; docs/audits/INDEX.md records the same set.
HISTORICAL_BROKEN_LINKS = frozenset(
    {
        "docs/audits/archive/AUDIT_WAVE120.md:539 -> memory/wave121_backlog.md",
        "docs/audits/archive/AUDIT_WAVE140.md:382 -> "
        "docs/plans/2026-05-11-wave140-tier123-design.md",
        "docs/audits/archive/AUDIT_WAVE140.md:581 -> "
        "docs/plans/2026-05-11-wave140-tier123-design.md",
        "docs/audits/archive/AUDIT_WAVE143.md:38 -> "
        "../../tests/test_wave143_jwks_roundtrip.py",
        "docs/audits/archive/AUDIT_WAVE143.md:124 -> "
        "../../frontend/scripts/wave138-visual-audit.mjs",
        "docs/audits/archive/AUDIT_WAVE143.md:317 -> "
        "../../tests/test_wave143_jwks_roundtrip.py",
        "docs/audits/archive/AUDIT_WAVE145.md:15 -> "
        "../../frontend/scripts/wave138-visual-audit.mjs:384",
        "docs/audits/archive/AUDIT_WAVE145.md:260 -> "
        "../plans/2026-05-12-wave145-tier15-design.md",
        "docs/audits/archive/AUDIT_WAVE163.md:28 -> ../../C:\\Users\\egorribun"
        ".claude\\projects\\C--Users-egorribun-Documents-university-ecosystem"
        "\\memory\\wave163_opening_prompt.md",
        "docs/audits/archive/AUDIT_WAVE192.md:272 -> .claude",
        "docs/audits/archive/AUDIT_WAVE192.md:273 -> .claude",
        "docs/audits/archive/AUDIT_WAVE192.md:274 -> .claude",
    }
)


def test_find_missing_reports_relative_file_target(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text("[missing](docs/missing.md)\n", encoding="utf-8")

    assert find_missing(tmp_path, [document]) == ["README.md:1 -> docs/missing.md"]


def test_find_missing_accepts_existing_files_and_external_links(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "guide.md"
    target.parent.mkdir()
    target.write_text("# Guide\n\n## Setup\n", encoding="utf-8")
    document = tmp_path / "README.md"
    document.write_text(
        "[guide](docs/guide.md#setup)\n[site](https://example.test/docs)\n",
        encoding="utf-8",
    )

    assert find_missing(tmp_path, [document]) == []


def test_find_missing_handles_reference_and_html_links(tmp_path: Path) -> None:
    target = tmp_path / "CONTRIBUTING.md"
    target.write_text("# Contributing\n", encoding="utf-8")
    document = tmp_path / "README.md"
    document.write_text(
        "[contributing]: CONTRIBUTING.md\n"
        '<a href="LICENSE">license</a> <img src="logo.svg">\n',
        encoding="utf-8",
    )

    assert find_missing(tmp_path, [document]) == [
        "README.md:2 -> LICENSE",
        "README.md:2 -> logo.svg",
    ]


def test_find_missing_can_include_archived_documents(tmp_path: Path) -> None:
    target = tmp_path / "frontend" / "src" / "main.tsx"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")
    document = tmp_path / "docs" / "audits" / "archive" / "AUDIT.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        "[source](../../../frontend/src/main.tsx)\n[gone](../../../gone.md)\n",
        encoding="utf-8",
    )

    assert find_missing(tmp_path, [document]) == []
    assert find_missing(tmp_path, [document], include_archives=True) == [
        "docs/audits/archive/AUDIT.md:2 -> ../../../gone.md"
    ]


def test_find_missing_ignores_links_in_code_and_comments(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text(
        "The prose mentions `[link](missing-in-example.md)` as syntax.\n"
        "~~~markdown\n[fenced](missing-in-fence.md)\n```\n~~~\n"
        "<!-- [commented](missing-in-comment.md) -->\n"
        "The real link is [missing](missing.md).\n",
        encoding="utf-8",
    )

    assert find_missing(tmp_path, [document]) == ["README.md:7 -> missing.md"]


def test_find_missing_rejects_existing_but_untracked_targets(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "tracked.md").write_text("# Tracked\n", encoding="utf-8")
    (tmp_path / "docs" / "local-draft.md").write_text("# Draft\n", encoding="utf-8")
    document = tmp_path / "README.md"
    document.write_text(
        "[tracked](docs/tracked.md)\n[dir](docs)\n[draft](docs/local-draft.md)\n",
        encoding="utf-8",
    )
    tracked = {"README.md", "docs/tracked.md", "docs", "."}

    assert find_missing(tmp_path, [document], tracked=tracked) == [
        "README.md:3 -> docs/local-draft.md"
    ]
    assert find_missing(tmp_path, [document]) == []


def test_find_missing_checks_heading_anchors(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text(
        "# Быстрый старт (Docker)\n\nSetext Title\n------------\n\n"
        '## Run\n\n## Run\n\n<a id="custom"></a>\n',
        encoding="utf-8",
    )
    document = tmp_path / "README.md"
    document.write_text(
        "[ru](guide.md#быстрый-старт-docker) [setext](guide.md#setext-title)\n"
        "[dup](guide.md#run-1) [html](guide.md#custom) [code](main.py#L1)\n"
        "[encoded](guide.md#%D0%B1%D1%8B%D1%81%D1%82%D1%80%D1%8B%D0%B9-"
        "%D1%81%D1%82%D0%B0%D1%80%D1%82-docker)\n"
        "[stale](guide.md#setup) [self](#missing) [top](#top)\n\n# Top\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text("", encoding="utf-8")

    assert find_missing(tmp_path, [document]) == [
        "README.md:4 -> guide.md#setup",
        "README.md:4 -> #missing",
    ]


def test_heading_anchors_follow_github_slug_rules() -> None:
    assert github_slug("1. Workspace Architecture & Subsystem Layout") == (
        "1-workspace-architecture--subsystem-layout"
    )
    assert github_slug("`uv run` and [ADR-013](adr/ADR-013.md)") == (
        "uv-run-and-adr-013"
    )
    assert github_slug("snake_case __bold__ name") == "snake_case-bold-name"
    assert heading_anchors("---\ntitle: x\n---\n# Real ###\n```\n# Code\n```\n") == {
        "real"
    }


def test_authored_markdown_relative_links_resolve() -> None:
    documents = tracked_markdown(ROOT)
    tracked = tracked_targets(ROOT)
    names = {document.relative_to(ROOT).as_posix() for document in documents}
    if tracked is None or "docs/README.md" not in names:
        # QUALITY-123 @egorribun — mutmut's isolated copy and the test image
        # omit docs/ and the Git metadata; the full-suite checkout runs this.
        pytest.skip("authored documentation tree is unavailable in this checkout")

    missing = find_missing(ROOT, documents, include_archives=True, tracked=tracked)

    assert sorted(set(missing) - HISTORICAL_BROKEN_LINKS) == []
    assert sorted(HISTORICAL_BROKEN_LINKS - set(missing)) == [], (
        "a historical broken link was fixed or moved; update the allowlist and "
        "docs/audits/INDEX.md"
    )
