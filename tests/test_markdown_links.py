from __future__ import annotations

from pathlib import Path

from scripts.docs.check_markdown_links import find_missing


def test_find_missing_reports_relative_file_target(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text("[missing](docs/missing.md)\n", encoding="utf-8")

    assert find_missing(tmp_path, [document]) == ["README.md:1 -> docs/missing.md"]


def test_find_missing_accepts_existing_files_and_external_links(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "guide.md"
    target.parent.mkdir()
    target.write_text("# Guide\n", encoding="utf-8")
    document = tmp_path / "README.md"
    document.write_text(
        "[guide](docs/guide.md#setup)\n[site](https://example.test/docs)\n",
        encoding="utf-8",
    )

    assert find_missing(tmp_path, [document]) == []


def test_find_missing_handles_reference_links(tmp_path: Path) -> None:
    target = tmp_path / "CONTRIBUTING.md"
    target.write_text("# Contributing\n", encoding="utf-8")
    document = tmp_path / "README.md"
    document.write_text("[contributing]: CONTRIBUTING.md\n", encoding="utf-8")

    assert find_missing(tmp_path, [document]) == []


def test_find_missing_can_include_archived_documents(tmp_path: Path) -> None:
    target = tmp_path / "frontend" / "src" / "main.tsx"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")
    document = tmp_path / "docs" / "audits" / "archive" / "AUDIT.md"
    document.parent.mkdir(parents=True)
    document.write_text("[source](../../../frontend/src/main.tsx)\n", encoding="utf-8")

    assert find_missing(tmp_path, [document], include_archives=True) == []


def test_find_missing_ignores_links_in_code_spans(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text(
        "The prose mentions `[link](missing-in-example.md)` as syntax.\n"
        "The real link is [missing](missing.md).\n",
        encoding="utf-8",
    )

    assert find_missing(tmp_path, [document]) == ["README.md:2 -> missing.md"]


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
