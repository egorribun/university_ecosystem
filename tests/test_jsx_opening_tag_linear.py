from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from scripts.quality import check_orphans_and_anti_patterns as checker


@pytest.mark.parametrize(
    ("opening_tag", "expected_name"),
    [
        ("<Button />", "Button"),
        ("<Button.Subcomponent>", "Button.Subcomponent"),
        ("<svg:foreignObject />", "svg:foreignObject"),
        ("<Widget/>", "Widget"),
        ("<Widget-1 />", "Widget-1"),
        ("<Widget_Name />", "Widget_Name"),
        ("<_Internal />", "_Internal"),
        ("<$Component.test />", "$Component.test"),
        ("<Élement />", "Élement"),
        ("<E\u0301lement />", "E\u0301lement"),
        ("<Widget\u2003/>", "Widget"),
    ],
)
def test_jsx_opening_tag_matches_supported_names(
    opening_tag: str, expected_name: str
) -> None:
    match = checker._match_jsx_opening_tag(opening_tag, 0)

    assert match is not None
    assert match == (expected_name, 1 + len(expected_name))


@pytest.mark.parametrize(
    "opening_tag",
    [
        "plain text",
        "< Button />",
        "<",
        "<1Widget />",
        "<\u2003Widget />",
        "<Widget! />",
        "<Widget",
        "<Widget=1 />",
    ],
)
def test_jsx_opening_tag_rejects_invalid_starts_and_delimiters(
    opening_tag: str,
) -> None:
    assert checker._match_jsx_opening_tag(opening_tag, 0) is None


def test_jsx_opening_tag_rejects_out_of_range_offsets() -> None:
    assert checker._match_jsx_opening_tag("<Widget />", -1) is None
    assert checker._match_jsx_opening_tag("<Widget />", len("<Widget />")) is None


def test_jsx_opening_tag_scanner_is_bounded_for_long_malformed_names() -> None:
    process = multiprocessing.get_context("spawn").Process(
        target=_match_long_malformed_jsx_names, daemon=True
    )
    process.start()
    process.join(timeout=5.0)
    if process.is_alive():
        process.kill()
        process.join(timeout=5.0)

    assert process.exitcode == 0


def _match_long_malformed_jsx_names() -> None:
    assert checker._match_jsx_opening_tag("<é" + "é" * 96, 0) is None
    assert checker._match_jsx_opening_tag("<$" + "$" * 100_000, 0) is None


def test_component_ownership_survives_nested_jsx_before_its_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    relative = "frontend/src/components/__tests__/Button.test.tsx"
    test_file = repository / relative
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "const view = <Button icon={condition ? <Icon /> : null} />;\n"
        'import Button from "../Button";\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert checker.matches_source(relative, {"frontend/src/components/Button.tsx"}, [])
    assert not checker.matches_source(
        relative, {"frontend/src/components/Other.tsx"}, []
    )
