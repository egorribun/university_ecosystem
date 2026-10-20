"""Check provisioned trace-to-logs ranges against pinned Grafana semantics."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "duration_us",
    [0, 1, 1_000_000],
    ids=["zero-duration", "sub-millisecond", "one-second"],
)
def test_trace_to_logs_range_contains_short_span(duration_us: int) -> None:
    source = (
        ROOT
        / "infrastructure/observability/grafana/provisioning"
        / "datasources/datasources.yaml"
    )
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    matches = [
        datasource
        for datasource in document["datasources"]
        if datasource["uid"] == "tempo"
    ]
    assert len(matches) == 1
    assert matches[0]["type"] == "tempo"
    options = matches[0]["jsonData"]["tracesToLogs"]
    assert options["datasourceUid"] == "loki"

    shifts_ms = []
    for key in ("spanStartTimeShift", "spanEndTimeShift"):
        value = options[key]
        assert value in {"1h", "-1h"}
        shifts_ms.append(int(value[:-1]) * 3_600_000)

    # Grafana v13.2.3, createSpanLink.tsx:getTimeRangeFromSpan:
    # signed shifts are added before flooring to milliseconds. Loki only
    # extends equal endpoints; it does not repair an inverted range.
    span_start_us = 1_700_000_000_000_000
    span_start_ms = span_start_us // 1000
    span_end_ms = (span_start_us + duration_us) // 1000
    range_start_ms = span_start_ms + shifts_ms[0]
    range_end_ms = span_end_ms + shifts_ms[1]
    if range_start_ms == range_end_ms:
        range_end_ms += 1

    assert range_start_ms <= span_start_ms
    assert range_end_ms >= span_end_ms
    assert range_start_ms < range_end_ms
