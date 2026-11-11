"""Keep current-run verification, production and gating on one private snapshot.

This prepares local files only. Uploading and runtime proof remain separate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scripts.quality.zap_findings_gate import evaluate_alerts
from scripts.quality.zap_report_binding import verify_payload
from scripts.quality.zap_run_provenance import verify_run
from scripts.quality.zap_sarif_producer import produce_payload


@dataclass(frozen=True)
class PreparedPublication:
    """A private snapshot and its public files, not an external publication."""

    _payload: bytes = field(repr=False)
    _sarif: Path = field(repr=False)

    def enforce_threshold(self, summary: Path | None) -> int:
        """After uploads, check public files again and gate the original bytes."""
        return evaluate_alerts(verify_payload(self._payload, self._sarif), summary)


def prepare_publication(
    work: Path, identity: dict[str, str], nonce: str, target: str, destination: Path
) -> PreparedPublication:
    """Prepare only after current-run and exact-origin evidence validates."""
    if destination.resolve().is_relative_to(work.resolve()):
        raise ValueError("Public ZAP output must be separate from private run evidence")
    payload = verify_run(work, identity, nonce, target)
    produce_payload(payload, destination)
    verify_payload(payload, destination)
    return PreparedPublication(payload, destination)
