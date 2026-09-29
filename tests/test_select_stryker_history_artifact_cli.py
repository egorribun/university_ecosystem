"""Trust-bound historical Stryker timing advice never certifies mutations."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import stat
import zipfile
import zlib
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.quality import select_stryker_history_artifact_cli as history
from scripts.quality.download_stryker_cost_artifacts import HttpResponse, Request

REPO = "example/university-ecosystem"
SOURCE_SHA = "a" * 40
TESTED_SHA = "b" * 40
CURRENT_SOURCE_SHA = "c" * 40
CURRENT_TESTED_SHA = "d" * 40
WORKFLOW = ".github/workflows/ci.yml"
API = f"https://api.github.com/repos/{REPO}"
CDN = "https://pipelines.actions.githubusercontent.com/artifacts/test?signature=ok"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _wrapper(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "payload": payload,
        "payloadSha256": hashlib.sha256(_json_bytes(payload)).hexdigest(),
    }


def _zip(member_name: str, contents: bytes, *, extra: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        info = zipfile.ZipInfo(member_name)
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, contents)
        if extra:
            archive.writestr("unexpected.sh", b"echo unsafe")
    return output.getvalue()


def _fixtures() -> tuple[history.HistoryArguments, dict[str, Any], dict[str, Any]]:
    input_hashes = {
        "frontend/package-lock.json": "1" * 64,
        "frontend/stryker.config.mjs": "2" * 64,
        "frontend/src/example.ts": "3" * 64,
        "frontend/src/example.test.ts": "4" * 64,
        "quality/coverage-source-policy.json": "5" * 64,
    }
    config = {
        "path": "frontend/stryker.config.mjs",
        "sha256": "2" * 64,
        "instrumenterOptions": {"ignorers": ["presentation-class-names"]},
    }
    preflight = {
        "digest": "6" * 64,
        "files": {
            "src/example.ts": {
                "sourceSha256": "3" * 64,
                "mutantSignatures": ["example-1"],
            }
        },
    }
    toolchain = {
        "node": "v24.15.0",
        "platform": "linux",
        "arch": "x64",
        "stryker": "9.0.0",
        "instrumenter": "9.0.0",
        "vitest": "3.0.0",
    }
    current_revision = {
        "headSha": CURRENT_TESTED_SHA,
        "sourceHeadSha": CURRENT_SOURCE_SHA,
        "repositoryDirty": False,
        "inputHashes": input_hashes,
    }
    historic_revision = {
        **current_revision,
        "headSha": TESTED_SHA,
        "sourceHeadSha": SOURCE_SHA,
    }
    current = _wrapper(
        {
            "schemaVersion": "1.0",
            "workflow": {
                "runId": "900",
                "runAttempt": "1",
                "sha": CURRENT_TESTED_SHA,
                "sourceHeadSha": CURRENT_SOURCE_SHA,
            },
            "sourceRevision": current_revision,
            "config": config,
            "toolchain": toolchain,
            "preflight": preflight,
        }
    )
    historic = _wrapper(
        {
            "schemaVersion": "1.0",
            "sourceRevision": historic_revision,
            "config": config,
            "preflightDigest": preflight["digest"],
            "costs": [
                {
                    "file": "src/example.ts",
                    "sourceSha256": "3" * 64,
                    "mutantCount": 1,
                    "estimatedDurationMs": 1234,
                }
            ],
        }
    )
    historic_preflight = _wrapper(
        {
            "schemaVersion": "1.0",
            "workflow": {
                "runId": "800",
                "runAttempt": "1",
                "sha": TESTED_SHA,
                "sourceHeadSha": SOURCE_SHA,
            },
            "sourceRevision": historic_revision,
            "config": config,
            "toolchain": toolchain,
            "preflight": preflight,
        }
    )
    arguments = history.HistoryArguments(
        repository=REPO,
        current_run_id=900,
        current_run_attempt=1,
        current_source_sha=CURRENT_SOURCE_SHA,
        event="pull_request",
        workflow_path=WORKFLOW,
        branch="egorribun",
    )
    return arguments, current, {"cost": historic, "preflight": historic_preflight}


def _artifact(name: str, artifact_id: int, archive: bytes) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": name,
        "expired": False,
        "size_in_bytes": len(archive),
        "digest": f"sha256:{hashlib.sha256(archive).hexdigest()}",
        "workflow_run": {"id": 800, "head_sha": SOURCE_SHA},
    }


class Network:
    def __init__(
        self,
        cost: dict[str, Any],
        preflight: dict[str, Any],
        *,
        cost_archive: bytes | None = None,
        preflight_archive: bytes | None = None,
        artifact_override: dict[str, object] | None = None,
        extra_artifacts: list[dict[str, object]] | None = None,
    ) -> None:
        self.cost_archive = cost_archive or _zip(
            "HISTORICAL_COSTS.json", _json_bytes(cost)
        )
        self.preflight_archive = preflight_archive or _zip(
            "PREFLIGHT_ARTIFACT.json", _json_bytes(preflight)
        )
        self.artifact_override = artifact_override or {}
        self.extra_artifacts = extra_artifacts or []
        self.calls: list[str] = []
        self.created_at = datetime.now(UTC).isoformat()
        self.detail_only_field = False

    def __call__(self, request: Request, maximum_bytes: int) -> HttpResponse:
        self.calls.append(request.full_url)
        assert maximum_bytes > 0
        url = request.full_url
        if url == f"{API}/actions/runs/900":
            return self._json(
                {
                    "id": 900,
                    "run_attempt": 1,
                    "head_sha": CURRENT_SOURCE_SHA,
                    "event": "pull_request",
                    "path": WORKFLOW,
                    "head_branch": "egorribun",
                    "repository": {"full_name": REPO},
                }
            )
        if "/actions/workflows/ci.yml/runs?" in url:
            return self._json(
                {
                    "total_count": 1,
                    "workflow_runs": [
                        {
                            "id": 800,
                            "head_sha": SOURCE_SHA,
                            "event": "pull_request",
                            "path": WORKFLOW,
                            "head_branch": "egorribun",
                            "conclusion": "success",
                            "run_attempt": 1,
                            "created_at": self.created_at,
                            "repository": {"full_name": REPO},
                        }
                    ],
                }
            )
        if url == f"{API}/actions/runs/800":
            detail = {
                "id": 800,
                "head_sha": SOURCE_SHA,
                "event": "pull_request",
                "path": WORKFLOW,
                "head_branch": "egorribun",
                "conclusion": "success",
                "run_attempt": 1,
                "created_at": self.created_at,
                "repository": {"full_name": REPO},
            }
            if self.detail_only_field:
                detail["display_title"] = "detail-only GitHub field"
            return self._json(detail)
        if url.startswith(f"{API}/actions/runs/800/artifacts?"):
            artifacts = [
                _artifact(
                    f"frontend-mutation-historical-costs-800-1-{TESTED_SHA}",
                    11,
                    self.cost_archive,
                ),
                _artifact(
                    f"frontend-mutation-preflight-800-1-{TESTED_SHA}",
                    12,
                    self.preflight_archive,
                ),
                *self.extra_artifacts,
            ]
            artifacts[0].update(self.artifact_override)
            return self._json({"total_count": len(artifacts), "artifacts": artifacts})
        if url in {
            f"{API}/actions/artifacts/11/zip",
            f"{API}/actions/artifacts/12/zip",
        }:
            return HttpResponse(302, {"Location": CDN}, b"")
        if url == CDN:
            archive = (
                self.cost_archive
                if self.calls[-2].endswith("/11/zip")
                else self.preflight_archive
            )
            return HttpResponse(200, {}, archive)
        raise AssertionError(f"unexpected request {url}")

    @staticmethod
    def _json(value: object) -> HttpResponse:
        return HttpResponse(200, {}, json.dumps(value).encode())


def test_selects_compatible_older_run_as_advice_only() -> None:
    arguments, current, historic = _fixtures()
    network = Network(historic["cost"], historic["preflight"])

    result = history.select_historical_costs(
        arguments, current, token="token", request=network
    )

    assert result.candidate is not None
    assert result.candidate.run_id == 800
    assert result.candidate.costs == {"src/example.ts": 1234}
    assert (
        result.candidate.cost_artifact["payload"]["sourceRevision"]["headSha"]
        == TESTED_SHA
    )
    assert result.diagnostic == "compatible historical Stryker timing advice"


def test_prior_attempt_artifact_does_not_poison_current_attempt_pair() -> None:
    arguments, current, historic = _fixtures()
    earlier = _artifact(
        f"frontend-mutation-historical-costs-800-0-{'e' * 40}",
        13,
        _zip("HISTORICAL_COSTS.json", b"older attempt"),
    )
    network = Network(
        historic["cost"], historic["preflight"], extra_artifacts=[earlier]
    )

    result = history.select_historical_costs(
        arguments, current, token="token", request=network
    )

    assert result.candidate is not None
    assert result.candidate.costs == {"src/example.ts": 1234.0}


def test_optional_history_rejects_zip_decompression_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def corrupt_read(_archive: zipfile.ZipFile, _member: object) -> bytes:
        raise zlib.error("invalid compressed data")

    monkeypatch.setattr(zipfile.ZipFile, "read", corrupt_read)
    with pytest.raises(history.InvalidHistory, match="archive cannot be read safely"):
        history._one_zip_member(
            _zip("HISTORICAL_COSTS.json", b"safe"), "HISTORICAL_COSTS.json"
        )


def test_optional_history_rejects_huge_json_integer_as_invalid_history() -> None:
    with pytest.raises(history.InvalidHistory, match="malformed JSON payload"):
        history._json_object(b'{"integer": ' + b"9" * 5000 + b"}")


def test_offline_snapshot_selects_only_digest_checked_compatible_costs(
    tmp_path: Any,
) -> None:
    arguments, current, historic = _fixtures()
    cost_archive = _zip("HISTORICAL_COSTS.json", _json_bytes(historic["cost"]))
    preflight_archive = _zip(
        "PREFLIGHT_ARTIFACT.json", _json_bytes(historic["preflight"])
    )
    metadata = {
        "run": {
            "id": 800,
            "head_sha": SOURCE_SHA,
            "event": "pull_request",
            "path": WORKFLOW,
            "head_branch": "egorribun",
            "conclusion": "success",
            "run_attempt": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "repository": {"full_name": REPO},
        },
        "artifacts": [
            _artifact(
                f"frontend-mutation-historical-costs-800-1-{TESTED_SHA}",
                11,
                cost_archive,
            ),
            _artifact(
                f"frontend-mutation-preflight-800-1-{TESTED_SHA}", 12, preflight_archive
            ),
        ],
    }
    (tmp_path / "metadata.json").write_bytes(_json_bytes(metadata))
    (tmp_path / "historical-costs.zip").write_bytes(cost_archive)
    (tmp_path / "preflight.zip").write_bytes(preflight_archive)

    accepted = history.select_offline_historical_costs(arguments, current, tmp_path)
    assert accepted.candidate is not None
    assert accepted.candidate.costs == {"src/example.ts": 1234.0}

    (tmp_path / "historical-costs.zip").write_bytes(cost_archive + b"tampered")
    rejected = history.select_offline_historical_costs(arguments, current, tmp_path)
    assert rejected.candidate is None
    assert "archive digest mismatch" in rejected.diagnostic


def test_bounded_offline_candidates_try_next_after_rejected_first(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    arguments, current, original = _snapshot(source)
    root = tmp_path / "batch"
    root.mkdir()
    first = root / "candidate-0"
    second = root / "candidate-1"
    shutil.copytree(original, first)
    shutil.copytree(original, second)
    stale_cost = json.loads(
        history._one_zip_member(
            (first / "historical-costs.zip").read_bytes(), "HISTORICAL_COSTS.json"
        )
    )
    stale_cost["payload"]["costs"][0]["estimatedDurationMs"] = 0
    stale_cost["payloadSha256"] = hashlib.sha256(
        _json_bytes(stale_cost["payload"])
    ).hexdigest()
    stale_zip = _zip("HISTORICAL_COSTS.json", _json_bytes(stale_cost))
    (first / "historical-costs.zip").write_bytes(stale_zip)
    stale_metadata = json.loads((first / "metadata.json").read_bytes())
    stale_metadata["artifacts"][0]["size_in_bytes"] = len(stale_zip)
    stale_metadata["artifacts"][0]["digest"] = (
        "sha256:" + hashlib.sha256(stale_zip).hexdigest()
    )
    (first / "metadata.json").write_bytes(_json_bytes(stale_metadata))
    candidates = []
    for folder in (first, second):
        candidates.append(
            {
                "directory": folder.name,
                "digests": {
                    name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                    for name in (
                        "metadata.json",
                        "historical-costs.zip",
                        "preflight.zip",
                    )
                },
            }
        )
    manifest = _json_bytes({"schemaVersion": "1.0", "candidates": candidates})
    (root / "candidates.json").write_bytes(manifest)

    result = history.select_offline_historical_candidates(
        arguments, current, root, hashlib.sha256(manifest).hexdigest()
    )

    assert result.candidate is not None
    assert result.candidate.costs == {"src/example.ts": 1234.0}

    # A post-checkout process cannot alter a considered candidate and still
    # obtain advice from a later one: each considered sample is bound.
    (first / "metadata.json").write_bytes(
        (first / "metadata.json").read_bytes() + b"tampered"
    )
    tampered = history.select_offline_historical_candidates(
        arguments, current, root, hashlib.sha256(manifest).hexdigest()
    )
    assert tampered.candidate is None
    assert "trusted download" in tampered.diagnostic


def test_offline_candidate_manifest_requires_pre_checkout_digest(
    tmp_path: Path,
) -> None:
    arguments, current, _ = _fixtures()
    root = tmp_path / "batch"
    root.mkdir()
    manifest = _json_bytes({"schemaVersion": "1.0", "candidates": []})
    (root / "candidates.json").write_bytes(manifest)

    result = history.select_offline_historical_candidates(
        arguments, current, root, "0" * 64
    )

    assert result.candidate is None
    assert "trusted download" in result.diagnostic


def test_offline_cli_accepts_only_pre_checkout_bound_candidate_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    arguments, current, original = _snapshot(source)
    root = tmp_path / "batch"
    root.mkdir()
    candidate = root / "candidate-0"
    shutil.copytree(original, candidate)
    manifest = _json_bytes(
        {
            "schemaVersion": "1.0",
            "candidates": [
                {
                    "directory": candidate.name,
                    "digests": {
                        name: hashlib.sha256(
                            (candidate / name).read_bytes()
                        ).hexdigest()
                        for name in (
                            "metadata.json",
                            "historical-costs.zip",
                            "preflight.zip",
                        )
                    },
                }
            ],
        }
    )
    (root / "candidates.json").write_bytes(manifest)
    current_path = tmp_path / "PREFLIGHT_ARTIFACT.json"
    current_path.write_bytes(_json_bytes(current))

    code = history.main(
        [
            "--repository",
            arguments.repository,
            "--current-run-id",
            str(arguments.current_run_id),
            "--current-run-attempt",
            str(arguments.current_run_attempt),
            "--current-source-sha",
            arguments.current_source_sha,
            "--event",
            arguments.event,
            "--workflow-path",
            arguments.workflow_path,
            "--branch",
            arguments.branch,
            "--current-preflight",
            str(current_path),
            "--offline-snapshot",
            str(root),
            "--snapshot-candidates-sha256",
            hashlib.sha256(manifest).hexdigest(),
        ],
        token=None,
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["candidate_run_id"] == 800


def test_offline_cli_writes_only_vetted_advice_without_token(
    tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments, current, historic = _fixtures()
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    cost_archive = _zip("HISTORICAL_COSTS.json", _json_bytes(historic["cost"]))
    preflight_archive = _zip(
        "PREFLIGHT_ARTIFACT.json", _json_bytes(historic["preflight"])
    )
    metadata = {
        "run": {
            "id": 800,
            "head_sha": SOURCE_SHA,
            "event": "pull_request",
            "path": WORKFLOW,
            "head_branch": arguments.branch,
            "conclusion": "success",
            "run_attempt": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "repository": {"full_name": REPO},
        },
        "artifacts": [
            _artifact(
                f"frontend-mutation-historical-costs-800-1-{TESTED_SHA}",
                11,
                cost_archive,
            ),
            _artifact(
                f"frontend-mutation-preflight-800-1-{TESTED_SHA}", 12, preflight_archive
            ),
        ],
    }
    (snapshot / "metadata.json").write_bytes(_json_bytes(metadata))
    (snapshot / "historical-costs.zip").write_bytes(cost_archive)
    (snapshot / "preflight.zip").write_bytes(preflight_archive)
    trusted_digests = {
        name: hashlib.sha256((snapshot / name).read_bytes()).hexdigest()
        for name in ("metadata.json", "historical-costs.zip", "preflight.zip")
    }
    preflight_path = tmp_path / "PREFLIGHT_ARTIFACT.json"
    preflight_path.write_bytes(_json_bytes(current))
    github_output = tmp_path / "github-output"
    github_output.write_text("", encoding="utf-8")
    receipt_path = tmp_path / "cross-run-receipt.json"

    code = history.main(
        [
            "--repository",
            arguments.repository,
            "--current-run-id",
            str(arguments.current_run_id),
            "--current-run-attempt",
            str(arguments.current_run_attempt),
            "--current-source-sha",
            arguments.current_source_sha,
            "--event",
            arguments.event,
            "--workflow-path",
            arguments.workflow_path,
            "--branch",
            arguments.branch,
            "--current-preflight",
            str(preflight_path),
            "--offline-snapshot",
            str(snapshot),
            "--snapshot-metadata-sha256",
            trusted_digests["metadata.json"],
            "--snapshot-cost-sha256",
            trusted_digests["historical-costs.zip"],
            "--snapshot-preflight-sha256",
            trusted_digests["preflight.zip"],
            "--output-receipt",
            str(receipt_path),
            "--github-output",
            str(github_output),
        ],
        token=None,
    )

    assert code == 0
    assert github_output.read_text(encoding="utf-8") == "has_candidate=true\n"
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["costs"] == {
        "src/example.ts": 1234.0
    }
    assert json.loads(capsys.readouterr().out)["has_candidate"] is True

    # A post-checkout process cannot replace metadata and recompute its own
    # artifact digests: the trusted action output binds the original bytes.
    (snapshot / "metadata.json").write_bytes(_json_bytes(metadata) + b" ")
    tampered = history.select_offline_historical_costs(
        arguments, current, snapshot, trusted_digests
    )
    assert tampered.candidate is None
    assert "differs from trusted download" in tampered.diagnostic


def test_run_detail_may_contain_additional_github_fields() -> None:
    arguments, current, historic = _fixtures()
    network = Network(historic["cost"], historic["preflight"])
    network.detail_only_field = True

    result = history.select_historical_costs(
        arguments, current, token="token", request=network
    )

    assert result.candidate is not None


def test_current_preflight_rejects_mismatched_tested_sha() -> None:
    arguments, current, historic = _fixtures()
    current["payload"]["sourceRevision"]["headSha"] = "e" * 40
    current["payloadSha256"] = hashlib.sha256(
        _json_bytes(current["payload"])
    ).hexdigest()

    with pytest.raises(history.InvalidHistory, match="current preflight provenance"):
        history.select_historical_costs(
            arguments,
            current,
            token="token",
            request=Network(historic["cost"], historic["preflight"]),
        )


@pytest.mark.parametrize("malformed", [None, [], "revision"])
def test_current_preflight_rejects_malformed_revision(malformed: object) -> None:
    arguments, current, historic = _fixtures()
    current["payload"]["sourceRevision"] = malformed
    current["payloadSha256"] = hashlib.sha256(
        _json_bytes(current["payload"])
    ).hexdigest()

    with pytest.raises(history.InvalidHistory, match="current preflight provenance"):
        history.select_historical_costs(
            arguments,
            current,
            token="token",
            request=Network(historic["cost"], historic["preflight"]),
        )


@pytest.mark.parametrize("malformed", [None, [], "preflight"])
def test_compatibility_rejects_malformed_current_preflight(malformed: object) -> None:
    _, current, historic = _fixtures()
    current["payload"]["preflight"] = malformed

    with pytest.raises(history.InvalidHistory, match="current viable source inventory"):
        history._compatible_costs(
            current,
            historic["cost"],
            historic["preflight"],
            {"id": 800, "run_attempt": 1, "head_sha": SOURCE_SHA},
            TESTED_SHA,
        )


@pytest.mark.parametrize(
    ("cost", "js_number", "digest"),
    [
        # Public SHA-256 golden values from the fixed synthetic fixture below;
        # none is a credential or an authentication key.
        (
            1234.0,
            "1234",
            "d755f4d878fb73e24fe5d21192fb0fcf312e35c2f5f8c475544b2ba773705d74",  # pragma: allowlist secret
        ),
        (
            1234.5,
            "1234.5",
            "bff7aff0aef413686aadc71c4fa604cb23750f4b46e83d7d6a30a8d73a5e44f4",  # pragma: allowlist secret
        ),
        (
            1234 / 7,
            "176.28571428571428",
            "11461883d6ec859d799c9937097d18dedf759afb821e279a5c68fb6ca8246c8a",  # pragma: allowlist secret
        ),
        (
            0.000001,
            "0.000001",
            "96fae0a43a95e9644442cea12c2e82af861439a6592ed7ffdcd292738eb31f3d",  # pragma: allowlist secret
        ),
        (
            0.0000001,
            "1e-7",
            "57292c7967611d7ff02798fd056a6fc5440db4958781240b03109078b0008a5f",  # pragma: allowlist secret
        ),
    ],
)
def test_verifies_real_stryker_cost_artifact_producer(
    cost: float, js_number: str, digest: str
) -> None:
    # Digests captured from buildHistoricalCostArtifact in run-stryker.mjs with
    # one BooleanLiteral mutant at src/example.ts and the fixed inputs below.
    payload = {
        "schemaVersion": "1.0",
        "sourceRevision": {
            "headSha": "b" * 40,
            "sourceHeadSha": "a" * 40,
            "repositoryDirty": False,
            "inputHashes": {},
        },
        "config": {},
        "preflightDigest": "83256cee576e5e9a801fbe0ba9ac21b6c1cb23795826ef611782b64efd2deade",  # pragma: allowlist secret
        "costs": [
            {
                "file": "src/example.ts",
                "sourceSha256": "3" * 64,
                "mutantCount": 1,
                "estimatedDurationMs": cost,
            }
        ],
    }
    raw = _json_bytes(
        {"schemaVersion": "1.0", "payload": payload, "payloadSha256": digest}
    )
    raw = raw.replace(
        f'"estimatedDurationMs": {json.dumps(cost)}'.encode(),
        f'"estimatedDurationMs": {js_number}'.encode(),
    )

    assert (
        history._verified_wrapper(raw)["payload"]["costs"][0]["estimatedDurationMs"]
        == cost
    )


def test_malformed_viable_inventory_never_selects_history() -> None:
    arguments, current, historic = _fixtures()
    malformed = {"sourceSha256": "7" * 64, "mutantSignatures": "not-an-array"}
    current["payload"]["preflight"]["files"]["src/another.ts"] = malformed
    historic["preflight"]["payload"]["preflight"]["files"]["src/another.ts"] = deepcopy(
        malformed
    )
    current["payloadSha256"] = hashlib.sha256(
        _json_bytes(current["payload"])
    ).hexdigest()
    historic["preflight"]["payloadSha256"] = hashlib.sha256(
        _json_bytes(historic["preflight"]["payload"])
    ).hexdigest()

    result = history.select_historical_costs(
        arguments,
        current,
        token="token",
        request=Network(historic["cost"], historic["preflight"]),
    )

    assert result.candidate is None
    assert "baseline planner retained" in result.diagnostic


def test_cli_reports_advice_without_reusing_mutation_evidence(
    tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments, current, historic = _fixtures()
    preflight_path = tmp_path / "PREFLIGHT_ARTIFACT.json"
    preflight_path.write_bytes(_json_bytes(current))
    network = Network(historic["cost"], historic["preflight"])

    code = history.main(
        [
            "--repository",
            arguments.repository,
            "--current-run-id",
            str(arguments.current_run_id),
            "--current-run-attempt",
            str(arguments.current_run_attempt),
            "--current-source-sha",
            arguments.current_source_sha,
            "--event",
            arguments.event,
            "--workflow-path",
            arguments.workflow_path,
            "--branch",
            arguments.branch,
            "--current-preflight",
            str(preflight_path),
        ],
        token="token",
        request=network,
    )

    assert code == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "has_candidate": True,
        "candidate_run_id": 800,
        "costs": {"src/example.ts": 1234.0},
        "diagnostic": "compatible historical Stryker timing advice",
    }


def test_github_api_outage_keeps_deterministic_baseline() -> None:
    arguments, current, _ = _fixtures()

    def unavailable(_: Request, __: int) -> HttpResponse:
        raise OSError("transient network outage")

    result = history.select_historical_costs(
        arguments, current, token="token", request=unavailable
    )

    assert result.candidate is None
    assert "baseline planner retained" in result.diagnostic


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "../university-ecosystem"),
        ("repository", "example/.."),
        ("workflow_path", ".github/workflows/../release.yml"),
        ("workflow_path", ".github/workflows/"),
        ("workflow_path", ".github/workflows/ci.yml/extra"),
    ],
)
def test_selector_rejects_repository_and_workflow_path_traversal(
    field: str, value: str
) -> None:
    arguments, current, historic = _fixtures()

    with pytest.raises(history.InvalidHistory, match="current workflow arguments"):
        history.select_historical_costs(
            replace(arguments, **{field: value}),
            current,
            token="token",
            request=Network(historic["cost"], historic["preflight"]),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "source-fingerprint",
        "toolchain",
        "preflight-inventory",
        "missing-cost",
        "nonfinite-cost",
        "wrong-producer-sha",
        "archive-digest",
        "extra-archive-entry",
    ],
)
def test_untrusted_or_incomplete_history_falls_back_to_baseline(mutation: str) -> None:
    arguments, current, historic = _fixtures()
    cost = deepcopy(historic["cost"])
    preflight = deepcopy(historic["preflight"])
    overrides: dict[str, object] = {}
    archive: bytes | None = None
    if mutation == "source-fingerprint":
        cost["payload"]["sourceRevision"]["inputHashes"][
            "frontend/src/example.test.ts"
        ] = "9" * 64
        preflight["payload"]["sourceRevision"]["inputHashes"][
            "frontend/src/example.test.ts"
        ] = "9" * 64
    elif mutation == "toolchain":
        preflight["payload"]["toolchain"]["node"] = "v22.0.0"
    elif mutation == "preflight-inventory":
        cost["payload"]["preflightDigest"] = "9" * 64
        preflight["payload"]["preflight"]["digest"] = "9" * 64
    elif mutation == "missing-cost":
        cost["payload"]["costs"] = []
    elif mutation == "nonfinite-cost":
        cost["payload"]["costs"][0]["estimatedDurationMs"] = float("inf")
    elif mutation == "wrong-producer-sha":
        overrides["workflow_run"] = {"id": 800, "head_sha": "f" * 40}
    elif mutation == "archive-digest":
        overrides["digest"] = "sha256:" + "f" * 64
    elif mutation == "extra-archive-entry":
        archive = _zip("HISTORICAL_COSTS.json", _json_bytes(cost), extra=True)
    for value in (cost, preflight):
        value["payloadSha256"] = hashlib.sha256(
            _json_bytes(value["payload"])
        ).hexdigest()
    network = Network(
        cost, preflight, cost_archive=archive, artifact_override=overrides
    )

    result = history.select_historical_costs(
        arguments, current, token="token", request=network
    )

    assert result.candidate is None
    assert result.diagnostic != "compatible historical Stryker timing advice"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b'{"a": 1, "a": 2}', "duplicate JSON key"),
        (b"", "JSON payload size"),
        (b"[]", "must be an object"),
        (b'{"x": NaN}', "nonfinite JSON constant"),
        (b"\xff", "malformed JSON payload"),
    ],
)
def test_json_boundaries_reject_ambiguous_or_invalid_documents(
    raw: bytes, message: str
) -> None:
    with pytest.raises(history.InvalidHistory, match=message):
        history._json_object(raw)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item.pop("payloadSha256"), "wrapper shape"),
        (lambda item: item.update(schemaVersion="2.0"), "schema is unsupported"),
        (lambda item: item.update(payload=[]), "schema is unsupported"),
        (lambda item: item.update(payloadSha256="x"), "digest is malformed"),
        (lambda item: item.update(payloadSha256=42), "digest is malformed"),
        (lambda item: item["payload"].update(changed=True), "digest mismatch"),
    ],
)
def test_wrapper_rejects_untrusted_structure(mutate: Any, message: str) -> None:
    item = _wrapper({"value": 1})
    mutate(item)
    with pytest.raises(history.InvalidHistory, match=message):
        history._verified_wrapper(_json_bytes(item))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            b'{"schemaVersion":"1.0","payload":{},"payloadSha256":"'
            + b"0" * 64
            + b'"}',
            "layout is not canonical",
        ),
        (
            b'{\n  "schemaVersion": "1.0",\n  "payload": [],\n  "payloadSha256": "'
            + b"0" * 64
            + b'"\n}\n',
            "schema is unsupported",
        ),
    ],
)
def test_wrapper_rejects_noncanonical_layout(raw: bytes, message: str) -> None:
    with pytest.raises(history.InvalidHistory, match=message):
        history._verified_wrapper(raw)


def test_request_budget_rejects_exhaustion_deadline_types_and_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Request(f"{API}/actions/runs/1")
    bounded = history._bounded_request(
        lambda _item, _limit: HttpResponse(200, {}, b"ok")
    )
    for _ in range(history._MAX_CALLS):
        assert bounded(request, 2).body == b"ok"
    with pytest.raises(history.InvalidHistory, match="budget exhausted"):
        bounded(request, 2)
    monkeypatch.setattr(history.time, "monotonic", lambda: float("inf"))
    with pytest.raises(history.InvalidHistory, match="budget exhausted"):
        history._bounded_request(lambda _item, _limit: HttpResponse(200, {}, b""))(
            request, 1
        )
    monkeypatch.undo()
    for response in [HttpResponse(200, {}, "bad"), HttpResponse(200, {}, b"too long")]:
        bounded = history._bounded_request(
            lambda _item, _limit, response=response: response
        )
        with pytest.raises(history.InvalidHistory, match=r"transport type|byte bound"):
            bounded(request, 1)


def test_request_rejects_deadline_after_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter((0.0, 0.0, history._MAX_SECONDS + 1))
    monkeypatch.setattr(history.time, "monotonic", lambda: next(ticks))
    request = history._bounded_request(lambda _item, _limit: HttpResponse(200, {}, b""))
    with pytest.raises(history.InvalidHistory, match="deadline"):
        request(Request(f"{API}/actions/runs/1"), 1)


def test_api_json_rejects_unsuccessful_status() -> None:
    with pytest.raises(history.InvalidHistory, match="non-success"):
        history._api_json(
            API, "token", lambda _item, _limit: HttpResponse(503, {}, b"{}")
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True),
        ("id", 99),
        ("event", "push"),
        ("path", "ci.yml"),
        ("head_branch", "other"),
        ("repository", None),
        ("repository", {"full_name": "other/repo"}),
        ("head_sha", 42),
        ("head_sha", "bad"),
        ("run_attempt", True),
        ("run_attempt", 0),
    ],
)
def test_run_identity_requires_exact_provenance(field: str, value: object) -> None:
    arguments, _, _ = _fixtures()
    run: dict[str, Any] = {
        "id": 800,
        "event": arguments.event,
        "path": arguments.workflow_path,
        "head_branch": arguments.branch,
        "repository": {"full_name": REPO},
        "head_sha": SOURCE_SHA,
        "run_attempt": 1,
    }
    run[field] = value
    with pytest.raises(history.InvalidHistory, match="identity mismatch"):
        history._identity(run, arguments, 800)


@pytest.mark.parametrize(
    "created", [None, "not-a-date", "2026-01-01", "2000-01-01T00:00:00Z"]
)
def test_run_age_rejects_missing_malformed_naive_or_stale_dates(
    created: object,
) -> None:
    assert history._age_is_valid({"created_at": created}, datetime.now(UTC)) is False


def test_run_age_rejects_future_date() -> None:
    assert (
        history._age_is_valid(
            {"created_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
            datetime.now(UTC),
        )
        is False
    )


@pytest.mark.parametrize(
    ("records", "message"),
    [
        (["not an artifact"], "entry is malformed"),
        ([{"name": 42}], "name is malformed"),
        ([], "pair is incomplete"),
    ],
)
def test_artifact_pair_rejects_invalid_inventory(
    records: list[object], message: str
) -> None:
    with pytest.raises(history.InvalidHistory, match=message):
        history._artifact_pair(
            records, {"id": 800, "run_attempt": 1, "head_sha": SOURCE_SHA}
        )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        (
            f"frontend-mutation-historical-costs-800-1-{'x' * 40}",
            "malformed historical artifact identity",
        ),
        (f"frontend-mutation-preflight-800-1-{'e' * 40}", "different tested SHAs"),
    ],
)
def test_artifact_pair_rejects_invalid_identity(name: str, message: str) -> None:
    first = _artifact(
        f"frontend-mutation-historical-costs-800-1-{TESTED_SHA}", 11, b"zip"
    )
    second = _artifact(name, 12, b"zip")
    with pytest.raises(history.InvalidHistory, match=message):
        history._artifact_pair(
            [first, second], {"id": 800, "run_attempt": 1, "head_sha": SOURCE_SHA}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 0),
        ("id", True),
        ("size_in_bytes", 0),
        ("size_in_bytes", True),
        ("expired", True),
        ("digest", "sha256:bad"),
        ("digest", 7),
        ("workflow_run", None),
        ("workflow_run", {"id": 800, "head_sha": "f" * 40}),
    ],
)
def test_artifact_pair_rejects_invalid_provenance(field: str, value: object) -> None:
    item = _artifact(
        f"frontend-mutation-historical-costs-800-1-{TESTED_SHA}", 11, b"zip"
    )
    item[field] = value
    with pytest.raises(history.InvalidHistory, match="provenance is invalid"):
        history._artifact_pair(
            [item], {"id": 800, "run_attempt": 1, "head_sha": SOURCE_SHA}
        )


@pytest.mark.parametrize(
    ("member", "contents", "expected", "message"),
    [
        ("unexpected.json", b"ok", "HISTORICAL_COSTS.json", "unexpected members"),
        ("HISTORICAL_COSTS.json", b"", "HISTORICAL_COSTS.json", "member is unsafe"),
    ],
)
def test_zip_member_rejects_wrong_name_or_empty_payload(
    member: str, contents: bytes, expected: str, message: str
) -> None:
    with pytest.raises(history.InvalidHistory, match=message):
        history._one_zip_member(_zip(member, contents), expected)


def test_zip_member_rejects_corrupt_archive() -> None:
    with pytest.raises(history.InvalidHistory, match="cannot be read safely"):
        history._one_zip_member(b"not a zip", "HISTORICAL_COSTS.json")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sourceRevision", None, "source revision is malformed"),
        ("costs", None, "timing is incomplete"),
        ("costs", [{"file": "src/example.ts"}], "cost entry is malformed"),
        (
            "costs",
            [
                {
                    "file": "src/example.ts",
                    "sourceSha256": "3" * 64,
                    "mutantCount": 1,
                    "estimatedDurationMs": -1,
                }
            ],
            "stale or nonfinite",
        ),
    ],
)
def test_cost_compatibility_rejects_malformed_or_unsafe_advice(
    field: str, value: object, message: str
) -> None:
    _, current, historic = _fixtures()
    historic["cost"]["payload"][field] = value
    with pytest.raises(history.InvalidHistory, match=message):
        history._compatible_costs(
            current,
            historic["cost"],
            historic["preflight"],
            {"id": 800, "run_attempt": 1, "head_sha": SOURCE_SHA},
            TESTED_SHA,
        )


@pytest.mark.parametrize(
    ("file", "entry"),
    [
        ("../escape.ts", {"sourceSha256": "3" * 64, "mutantSignatures": ["one"]}),
        (
            "src/example.ts",
            {"sourceSha256": "3" * 64, "mutantSignatures": ["same", "same"]},
        ),
        ("src/example.ts", {"sourceSha256": "bad", "mutantSignatures": ["one"]}),
    ],
)
def test_cost_compatibility_rejects_malformed_viable_source_inventory(
    file: str, entry: dict[str, object]
) -> None:
    _, current, historic = _fixtures()
    current["payload"]["preflight"]["files"] = {file: entry}
    with pytest.raises(
        history.InvalidHistory, match="source inventory entry is malformed"
    ):
        history._compatible_costs(
            current,
            historic["cost"],
            historic["preflight"],
            {"id": 800, "run_attempt": 1, "head_sha": SOURCE_SHA},
            TESTED_SHA,
        )


def _snapshot(tmp_path: Path) -> tuple[history.HistoryArguments, dict[str, Any], Path]:
    arguments, current, historic = _fixtures()
    root = tmp_path / "snapshot"
    root.mkdir()
    cost_zip = _zip("HISTORICAL_COSTS.json", _json_bytes(historic["cost"]))
    preflight_zip = _zip("PREFLIGHT_ARTIFACT.json", _json_bytes(historic["preflight"]))
    run = {
        "id": 800,
        "head_sha": SOURCE_SHA,
        "event": "pull_request",
        "path": WORKFLOW,
        "head_branch": arguments.branch,
        "conclusion": "success",
        "run_attempt": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "repository": {"full_name": REPO},
    }
    records = [
        _artifact(
            f"frontend-mutation-historical-costs-800-1-{TESTED_SHA}", 11, cost_zip
        ),
        _artifact(f"frontend-mutation-preflight-800-1-{TESTED_SHA}", 12, preflight_zip),
    ]
    (root / "metadata.json").write_bytes(
        _json_bytes({"run": run, "artifacts": records})
    )
    (root / "historical-costs.zip").write_bytes(cost_zip)
    (root / "preflight.zip").write_bytes(preflight_zip)
    return arguments, current, root


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda item: item.pop("run"), "metadata is malformed"),
        (lambda item: item.update(run=[]), "metadata is malformed"),
        (lambda item: item["run"].update(id=900), "run id is invalid"),
        (lambda item: item["run"].update(conclusion="failure"), "not a recent success"),
        (
            lambda item: item["run"].update(created_at="2000-01-01T00:00:00Z"),
            "not a recent success",
        ),
    ],
)
def test_offline_snapshot_rejects_malformed_or_stale_metadata(
    tmp_path: Path, change: Any, message: str
) -> None:
    arguments, current, root = _snapshot(tmp_path)
    metadata = root / "metadata.json"
    document = json.loads(metadata.read_text(encoding="utf-8"))
    change(document)
    metadata.write_bytes(_json_bytes(document))
    selected = history.select_offline_historical_costs(arguments, current, root)
    assert selected.candidate is None
    assert message in selected.diagnostic


def test_offline_snapshot_rejects_non_directory_root(tmp_path: Path) -> None:
    arguments, current, _ = _fixtures()
    root = tmp_path / "not-directory"
    root.write_text("unsafe", encoding="utf-8")
    result = history.select_offline_historical_costs(arguments, current, root)
    assert result.candidate is None
    assert "root is unsafe" in result.diagnostic


def test_snapshot_file_rejects_missing_directory_and_changed_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(history.InvalidHistory, match="cannot be read"):
        history._snapshot_file(tmp_path, "missing", 100)
    (tmp_path / "member").mkdir()
    with pytest.raises(history.InvalidHistory, match="member is unsafe"):
        history._snapshot_file(tmp_path, "member", 100)
    (tmp_path / "member").rmdir()
    target = tmp_path / "member"
    target.write_bytes(b"one")
    original_read = Path.read_bytes

    def changed_read(path: Path) -> bytes:
        if path == target:
            return b"changed"
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", changed_read)
    with pytest.raises(history.InvalidHistory, match="changed while reading"):
        history._snapshot_file(tmp_path, "member", 100)


def test_current_preflight_rejects_missing_or_nonregular_path(tmp_path: Path) -> None:
    with pytest.raises(history.InvalidHistory, match="cannot be read"):
        history._read_current_preflight(tmp_path / "missing")
    with pytest.raises(history.InvalidHistory, match="unlinked regular file"):
        history._read_current_preflight(tmp_path)


def test_cli_rejects_bad_current_preflight(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments, _, _ = _fixtures()
    bad = tmp_path / "bad.json"
    bad.write_text("not JSON", encoding="utf-8")
    code = history.main(
        [
            "--repository",
            arguments.repository,
            "--current-run-id",
            str(arguments.current_run_id),
            "--current-run-attempt",
            str(arguments.current_run_attempt),
            "--current-source-sha",
            arguments.current_source_sha,
            "--event",
            arguments.event,
            "--workflow-path",
            arguments.workflow_path,
            "--branch",
            arguments.branch,
            "--current-preflight",
            str(bad),
        ],
        token="token",
    )
    assert code == 1
    assert "malformed JSON payload" in capsys.readouterr().err
