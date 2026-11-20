"""Closed, bounded extraction of Events scroll geometry from live output."""

import itertools
from pathlib import Path

import pytest

from scripts import live_stand
from scripts import live_stand_playwright_evidence as evidence


def row(**overrides: str) -> str:
    fields = {
        "project": "mobile",
        "language": "ru",
        "attempt": "0",
        "phase": "before",
        "viewportWidth": "390",
        "viewportHeight": "844",
        "documentHeight": "6000",
        "scrollY": "2500",
        "gridTop": "-1800",
        "linkTop": "400",
        "linkHeight": "54",
        "selectedIndex": "2",
        "cardCount": "3",
        "heights": "410,411,412",
    }
    fields.update(overrides)
    return (
        "UE_LIVE_EVENTS_GEOMETRY_V1 "
        + " ".join(f"{key}={value}" for key, value in fields.items())
        + "\n"
    )


def test_events_geometry_accepts_only_bounded_numeric_samples() -> None:
    assert evidence._live_playwright_events_geometries(row().replace("\n", "\r\n")) == [
        {
            "project": "mobile",
            "language": "ru",
            "attempt": 0,
            "phase": "before",
            "viewportWidth": 390,
            "viewportHeight": 844,
            "documentHeight": 6000,
            "scrollY": 2500,
            "gridTop": -1800,
            "linkTop": 400,
            "linkHeight": 54,
            "selectedIndex": 2,
            "cardCount": 3,
            "heights": [410, 411, 412],
        }
    ]


@pytest.mark.parametrize(
    "invalid",
    [
        row(project="private"),
        row(language="de"),
        row(attempt="2"),
        row(phase="private"),
        row(viewportWidth="0"),
        row(linkTop="1000000"),
        row(cardCount="2"),
        row(selectedIndex="3"),
        row(heights="410,411"),
        row(heights="410,411,private"),
        row(heights="410,411,-1"),
        row()[:-1] + " extra=private\n",
        row()[:-1] + "\x00\n",
        row()[:-1] + "x" * 321 + "\n",
        row()[:-1],
    ],
)
def test_events_geometry_rejects_malformed_and_private_rows(invalid: str) -> None:
    assert evidence._live_playwright_events_geometries(invalid) == []


def test_events_geometry_deduplicates_and_caps_each_attempt_and_phase() -> None:
    rows = [
        row(project=project, language=language, attempt=attempt, phase=phase)
        for project, language, attempt, phase in itertools.product(
            ("desktop", "mobile"),
            ("ru", "en"),
            ("0", "1"),
            ("before", "back", "back-forward"),
        )
    ]
    parsed = evidence._live_playwright_events_geometries(
        rows[0] + rows[0] + "".join(rows)
    )
    assert len(parsed) == 24
    assert (
        len({(r["project"], r["language"], r["attempt"], r["phase"]) for r in parsed})
        == 24
    )


def test_events_geometry_caps_card_samples_at_twelve() -> None:
    sample = row(selectedIndex="15", cardCount="16", heights=",".join(["410"] * 12))
    assert len(evidence._live_playwright_events_geometries(sample)[0]["heights"]) == 12
    assert (
        evidence._live_playwright_events_geometries(
            row(cardCount="16", heights=",".join(["410"] * 13))
        )
        == []
    )


def test_events_geometry_accepts_maximal_values_and_rejects_oversized_lines() -> None:
    sample = row(
        project="desktop",
        phase="back-forward",
        viewportWidth="999999",
        viewportHeight="999999",
        documentHeight="999999",
        scrollY="999999",
        gridTop="-999999",
        linkTop="-999999",
        linkHeight="999999",
        selectedIndex="99",
        cardCount="100",
        heights=",".join(["999999"] * 12),
    )
    assert 320 < len(sample.rstrip("\n")) <= 384
    parsed = evidence._live_playwright_events_geometries(sample)
    assert len(parsed) == 1
    assert parsed[0]["selectedIndex"] == 99
    assert parsed[0]["heights"] == [999999] * 12

    oversized = sample.rstrip("\n") + "x" * 385 + "\n"
    assert len(oversized.rstrip("\n")) > 384
    assert evidence._live_playwright_events_geometries(oversized) == []


def test_live_runner_relays_only_validated_geometry(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    private = "private event title and raw error"

    def fake_run_check(check, **_kwargs):
        return live_stand.fast_preflight.CheckResult(
            name=check.name,
            command=tuple(check.command),
            status="failed",
            exit_code=1,
            duration_seconds=0.0,
            stdout=row() + row(heights="410,411,private") + private + "\n",
            stderr=private,
        )

    monkeypatch.setattr(live_stand.fast_preflight, "run_check", fake_run_check)
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    lines = printed.out.splitlines()
    assert sum(line.startswith("live E2E events geometry ") for line in lines) == 1
    assert '"heights":[410,411,412]' in next(
        line for line in lines if line.startswith("live E2E events geometry ")
    )
    assert private not in printed.out + printed.err
