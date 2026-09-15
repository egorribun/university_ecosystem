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
