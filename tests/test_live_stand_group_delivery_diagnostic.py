import json

from scripts import live_stand_playwright_evidence as evidence


def record():
    role = dict(
        sockets=1,
        closedSockets=0,
        joinSentSockets=1,
        openJoinSentSockets=1,
        pongAfterJoinSentSockets=1,
        targetFrames=1,
        matchingFrames=1,
        socketsCapped=False,
        framesCapped=False,
        pongBeforeSend=True,
    )
    return dict(
        schema=4,
        scenario="group-initial-delivery",
        project="desktop",
        attempt=0,
        owner=role.copy(),
        teacher=role.copy(),
        secondMember=role.copy(),
    )


def line(value, retained=False):
    prefix = "live E2E reconnect " if retained else "UE_LIVE_RECONNECT_V1 "
    return prefix + json.dumps(value) + "\n"


def test_group_record_survives_both_redaction_boundaries():
    value = record()
    assert evidence._live_playwright_reconnect_diagnostics(line(value)) == [value]
    assert evidence._live_playwright_reconnect_diagnostics(
        line(value, True), retained=True
    ) == [value]


def test_group_record_rejects_unknown_and_inconsistent_values():
    for delta in (
        {"private": "marker"},
        {"project": "untrusted"},
        {"schema": True},
        {"attempt": True},
        {"attempt": 2},
    ):
        assert (
            evidence._live_playwright_reconnect_diagnostics(line(record() | delta))
            == []
        )
    for delta in (
        {"extra": "marker"},
        {"sockets": 33},
        {"matchingFrames": 2},
        {"closedSockets": 2},
        {"openJoinSentSockets": 2},
        {"pongAfterJoinSentSockets": 2},
        {"targetFrames": True},
        {"socketsCapped": True},
        {"framesCapped": True},
        {"matchingFrames": "private-marker"},
    ):
        value = record()
        value["teacher"] |= delta
        assert evidence._live_playwright_reconnect_diagnostics(line(value)) == []
    raw = line(record())
    for bad in (
        raw.rstrip("\n"),
        raw.replace('"schema": 4', '"schema": 4, "schema": 4'),
        raw.replace('"schema": 4', '"schema": NaN'),
        " " + raw,
    ):
        assert evidence._live_playwright_reconnect_diagnostics(bad) == []


def test_group_record_is_deduplicated_and_output_is_bounded():
    values = [
        record() | {"project": project, "attempt": attempt}
        for project in ("desktop", "mobile")
        for attempt in (0, 1)
    ]
    parsed = evidence._live_playwright_reconnect_diagnostics(
        "".join(map(line, [values[0], values[0], *values[1:]]))
    )
    assert parsed == values
    overlong = line(record()).replace('"schema": 4', '"schema": 4' + " " * 5000)
    assert evidence._live_playwright_reconnect_diagnostics(overlong) == []


def test_capped_group_counts_must_be_internally_consistent():
    value = record()
    value["owner"] = dict(
        sockets=32,
        closedSockets=1,
        joinSentSockets=32,
        openJoinSentSockets=31,
        pongAfterJoinSentSockets=32,
        targetFrames=32,
        matchingFrames=10,
        socketsCapped=True,
        framesCapped=True,
        pongBeforeSend=False,
    )
    assert evidence._live_playwright_reconnect_diagnostics(line(value)) == [value]
    value["owner"]["openJoinSentSockets"] = 32
    assert evidence._live_playwright_reconnect_diagnostics(line(value)) == []


def test_existing_transport_schemas_remain_closed():
    forwarding = dict(
        schema=2,
        scenario="forwarding-source-receive",
        project="desktop",
        attempt=0,
        sockets=1,
        joinSentSockets=1,
        openJoinSentSockets=1,
        sourceFrames=1,
        sourceFramesAfterJoinSent=1,
        sourceAccepted=True,
        socketsCapped=False,
        framesCapped=False,
    )
    receipt = dict(
        schema=3,
        scenario="read-receipt-peer",
        project="desktop",
        attempt=0,
        sockets=1,
        closedSockets=0,
        latestUnclosedJoinSent=True,
        chatFrames=1,
        matchingFrames=1,
        socketsCapped=False,
        framesCapped=False,
    )
    assert evidence._live_playwright_reconnect_diagnostics(
        line(forwarding) + line(receipt)
    ) == [forwarding, receipt]
    assert (
        evidence._live_playwright_reconnect_diagnostics(
            line(forwarding | {"extra": "private"})
        )
        == []
    )
    assert (
        evidence._live_playwright_reconnect_diagnostics(
            line(receipt | {"matchingFrames": 2})
        )
        == []
    )
