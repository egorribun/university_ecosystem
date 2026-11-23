from __future__ import annotations

import subprocess
from itertools import product
from pathlib import Path

import pytest

from scripts import live_stand_playwright_evidence as evidence
from tests import test_live_stand as stand_tests


def test_push_recipient_records_are_closed_bounded_and_deduplicated() -> None:
    parse = getattr(evidence, "_live_playwright_push_recipient_observations", None)
    assert callable(parse)
    valid = (
        "UE_LIVE_PUSH_RECIPIENT_V1 project=mobile retry=0 scenario=news "
        "check=session-owner-match subscription=same\n"
    )
    assert parse(valid + valid) == [
        ("mobile", 0, "news", "session-owner-match", "same")
    ]
    assert parse(valid.replace("session-owner-match", "session-owner-mismatch")) == [
        ("mobile", 0, "news", "session-owner-mismatch", "same")
    ]
    for row in (
        valid[:-1],
        valid[:-1] + " private-token\n",
        valid.replace("scenario=news", "scenario=private-user"),
        valid.replace(
            "check=session-owner-match", "check=https://private.example/token"
        ),
        valid.replace("check=session-owner-match", "check=match"),
        valid.replace("check=session-owner-match", "check=mismatch"),
        valid.replace("retry=0", "retry=2"),
        "private " + valid,
        valid.replace("subscription=same", "subscription=same\x1b"),
    ):
        assert parse(row) == []


def test_push_recipient_records_have_a_run_wide_cap() -> None:
    rows = [
        f"UE_LIVE_PUSH_RECIPIENT_V1 project={project} retry={retry} "
        f"scenario={scenario} check={check} subscription=same\n"
        for project, retry, scenario, check in product(
            ("desktop", "mobile"),
            (0, 1),
            ("chat", "reply", "news", "events", "schedule", "release"),
            ("session-owner-match", "none"),
        )
    ]
    records = evidence._live_playwright_push_recipient_observations("".join(rows))
    assert len(records) == 32


def test_live_runner_relays_only_valid_push_recipient_classes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    row = (
        "UE_LIVE_PUSH_RECIPIENT_V1 project=mobile retry=0 scenario=news "
        "check=auth subscription=same\n"
    )
    private = "private endpoint user payload token"
    stand = stand_tests.live_stand
    result = subprocess.CompletedProcess(
        stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(row + private + "\n" + row.rstrip() + " " + private + "\n").encode(),
        stderr=(row + private + "\n").encode(),
    )
    stand_tests._patch_live_playwright_result(monkeypatch, result)
    with pytest.raises(stand.StandError, match="exit code 1"):
        stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    captured = capsys.readouterr()
    assert captured.out.count("live E2E push recipient project=mobile") == 1
    assert "retry=0 scenario=news check=auth subscription=same" in captured.out
    assert private not in captured.out + captured.err
    assert captured.err == ""


def test_rotation_records_are_bounded_closed_and_reject_conflicting_ordinals() -> None:
    parse = evidence._live_playwright_push_rotation_observations
    valid = (
        "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=0 scenario=news "
        "phase=before-wait ordinal=2 endpoint_sha256=0123456789ab\n"
    )
    expected = ("mobile", 0, "news", "before-wait", 2, "0123456789ab")
    assert parse(valid + valid) == [expected]
    for row in (
        valid[:-1],
        valid.rstrip() + " private\n",
        valid.rstrip() + "x" * 181 + "\n",
        valid.replace("ordinal=2", "ordinal=2\x1b"),
        "private " + valid,
        valid.replace("mobile", "private"),
        valid.replace("retry=0", "retry=2"),
        valid.replace("scenario=news", "scenario=private"),
        valid.replace("phase=before-wait", "phase=opt-in"),
        valid.replace("ordinal=2", "ordinal=9"),
        valid.replace("0123456789ab", "https://private"),
        valid.replace("0123456789ab", "0123456789AB"),
    ):
        assert parse(row) == []
    assert parse(valid + valid.replace("0123456789ab", "aaaaaaaaaaaa") + valid) == []
    setup = valid.replace(
        "scenario=news phase=before-wait", "scenario=setup phase=opt-in"
    )
    assert parse(setup)[0][2:4] == ("setup", "opt-in")
    assert parse(valid.replace("0123456789ab", "missing"))[0][-1] == "missing"
    assert parse(valid.replace("0123456789ab", "unavailable"))[0][-1] == "unavailable"
    rows = [
        valid.replace("mobile", project)
        .replace("retry=0", f"retry={retry}")
        .replace("ordinal=2", f"ordinal={ordinal}")
        for project, retry, ordinal in product(
            ("desktop", "mobile"), (0, 1), range(1, 9)
        )
    ]
    assert len(parse("".join(rows))) == 32


def test_reply_rotation_preserves_topic_records_with_matching_ordinals() -> None:
    parse = evidence._live_playwright_push_rotation_observations
    topic = (
        "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=0 scenario=setup "
        "phase=opt-in ordinal=1 endpoint_sha256=0123456789ab\n"
    )
    reply = (
        "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=0 scenario=reply "
        "phase=opt-in ordinal=1 endpoint_sha256=aaaaaaaaaaaa\n"
    )
    expected_topic = ("mobile", 0, "setup", "opt-in", 1, "0123456789ab")
    expected_reply = ("mobile", 0, "reply", "opt-in", 1, "aaaaaaaaaaaa")
    assert parse(topic + reply + reply) == [expected_topic, expected_reply]
    assert parse(reply.replace("phase=opt-in", "phase=before-wait")) == [
        ("mobile", 0, "reply", "before-wait", 1, "aaaaaaaaaaaa")
    ]
    assert parse(reply.replace("phase=opt-in", "phase=failure")) == [
        ("mobile", 0, "reply", "failure", 1, "aaaaaaaaaaaa")
    ]
    conflict = reply.replace("aaaaaaaaaaaa", "bbbbbbbbbbbb")
    assert parse(topic + reply + conflict + reply) == [expected_topic]
    conflicting_topic = topic.replace("scenario=setup", "scenario=news").replace(
        "phase=opt-in", "phase=before-wait"
    )
    assert parse(topic + conflicting_topic + reply) == [expected_reply]
    for invalid in (
        reply[:-1],
        reply.rstrip() + " private\n",
        reply.replace("aaaaaaaaaaaa", "https://private"),
        reply.replace("aaaaaaaaaaaa", "AAAAAAAAAAAA"),
        reply.replace("project=mobile", "project=desktop"),
        reply.replace("scenario=reply", "scenario=private"),
        reply.replace("phase=opt-in", "phase=private"),
    ):
        assert parse(invalid) == []


def test_live_runner_relays_rotation_prefix_only_from_closed_stdout_records(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = (
        "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=0 scenario=news "
        "phase=before-wait ordinal=2 endpoint_sha256=0123456789ab\n"
    )
    reply = row.replace("scenario=news", "scenario=reply").replace(
        "0123456789ab", "aaaaaaaaaaaa"
    )
    private = "private endpoint user payload token"
    stand = stand_tests.live_stand
    result = subprocess.CompletedProcess(
        stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(row + reply + row.rstrip() + " " + private + "\n").encode(),
        stderr=(row + private + "\n").encode(),
    )
    stand_tests._patch_live_playwright_result(monkeypatch, result)
    with pytest.raises(stand.StandError, match="exit code 1"):
        stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    captured = capsys.readouterr()
    assert captured.out.count("live E2E push rotation project=mobile") == 2
    assert "phase=before-wait ordinal=2 endpoint_sha256=0123456789ab" in captured.out
    assert (
        "scenario=reply phase=before-wait ordinal=2 endpoint_sha256=aaaaaaaaaaaa"
        in (captured.out)
    )
    assert private not in captured.out + captured.err
    assert captured.err == ""
