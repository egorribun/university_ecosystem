"""Contract checks for the file-processor JetStream durable and KEDA scaler."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / "charts" / "university-ecosystem" / "values.yaml"
SCALER_TEMPLATE = (
    ROOT / "charts" / "university-ecosystem" / "templates" / "keda-scaledobjects.yaml"
)
RUNTIME = ROOT / "services" / "file-processor" / "cmd" / "file-processor" / "main.go"


def _runtime_consumer_name() -> str:
    source = RUNTIME.read_text(encoding="utf-8")
    match = re.search(
        r"(?m)^\s*fileProcessConsumer\s*=\s*\"(?P<consumer>[^\"]+)\"\s*$",
        source,
    )
    assert match is not None, "runtime file-processor durable declaration is missing"
    return match.group("consumer")


def _values() -> dict[str, Any]:
    parsed = yaml.safe_load(VALUES.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_file_processor_keda_consumer_matches_runtime_durable() -> None:
    """KEDA must observe the durable that QueueSubscribe actually consumes."""
    file_processor = _values()["keda"]["fileProcessor"]["natsJetstream"]

    assert file_processor["enabled"] is True
    assert file_processor["stream"] == "FILES_PROCESS"
    assert file_processor["consumer"] == _runtime_consumer_name()
    assert file_processor["consumer"]


def test_file_processor_keda_template_uses_configured_consumer() -> None:
    """The chart must not replace the reviewed durable with a second literal."""
    template = SCALER_TEMPLATE.read_text(encoding="utf-8")

    assert (
        "consumer: {{ .Values.keda.fileProcessor.natsJetstream.consumer | quote }}"
        in template
    )
    assert 'consumer: "file-processor-worker"' not in template
    assert "fileProcessConsumer" in RUNTIME.read_text(encoding="utf-8")
