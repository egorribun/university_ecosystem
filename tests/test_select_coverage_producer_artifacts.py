from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.quality.select_coverage_producer_artifacts as selector
import scripts.quality.select_same_run_artifact_cli as same_run

REPOSITORY = "example/university-ecosystem"
RUN_ID = "123456789"
CONSUMER_ATTEMPT = "3"
COMMIT_SHA = "a" * 40
RUN_HEAD_SHA = "b" * 40
EVENT = "pull_request"
WORKFLOW_PATH = ".github/workflows/ci.yml"


class _Network:
    def __init__(self, responses: list[same_run.HttpResponse]) -> None:
        self.responses = iter(responses)
        self.requests: list[same_run.Request] = []

    def __call__(
        self, request: same_run.Request, maximum_bytes: int
    ) -> same_run.HttpResponse:
        del maximum_bytes
        self.requests.append(request)
        return next(self.responses)


def _response(payload: object) -> same_run.HttpResponse:
    return same_run.HttpResponse(
        status=200,
        headers={},
        body=json.dumps(payload).encode("utf-8"),
    )


def _arguments() -> selector.CoverageProducerArguments:
    return selector.CoverageProducerArguments(
        repository=REPOSITORY,
        run_id=RUN_ID,
        consumer_run_attempt=CONSUMER_ATTEMPT,
        commit_sha=COMMIT_SHA,
        run_head_sha=RUN_HEAD_SHA,
        event=EVENT,
        workflow_path=WORKFLOW_PATH,
    )


def _run_metadata() -> dict[str, object]:
    return {
        "id": int(RUN_ID),
        "head_sha": RUN_HEAD_SHA,
        "event": EVENT,
        "path": WORKFLOW_PATH,
        "run_attempt": int(CONSUMER_ATTEMPT),
        "repository": {"full_name": REPOSITORY},
    }


def _artifact(
    spec: selector.CoverageProducerSpec, attempt: int, artifact_id: int
) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": f"{spec.prefix}{attempt}",
        "size_in_bytes": 1,
        "expired": False,
        "digest": "sha256:" + "c" * 64,
        "workflow_run": {"id": int(RUN_ID), "head_sha": RUN_HEAD_SHA},
    }


def _network(artifacts: list[dict[str, object]]) -> _Network:
    return _Network(
        [
            _response(_run_metadata()),
            _response({"total_count": len(artifacts), "artifacts": artifacts}),
        ]
    )


def test_selects_latest_valid_candidate_for_every_producer_from_one_snapshot() -> None:
    artifacts: list[dict[str, object]] = []
    next_id = 10
    for spec in selector.COVERAGE_PRODUCER_SPECS:
        artifacts.append(_artifact(spec, 1, next_id))
        next_id += 1
        if spec.key in {"backend_shard_0", "go_gateway"}:
            artifacts.append(_artifact(spec, 2, next_id))
            next_id += 1

    network = _network(artifacts)
    selected = selector.select_coverage_producers(
        _arguments(), token="test-token", request=network
    )

    assert selected["backend_shard_0"]["producer_attempt"] == 2
    assert selected["go_gateway"]["producer_attempt"] == 2
    assert selected["backend_shard_1"]["producer_attempt"] == 1
    assert selected["rust_coverage"]["producer_attempt"] == 1
    assert selected["rust_codecov"]["producer_attempt"] == 1
    assert len(network.requests) == 2


def test_duplicate_attempt_is_rejected_fail_closed() -> None:
    spec = selector.COVERAGE_PRODUCER_SPECS[0]
    artifacts = [_artifact(spec, 1, 10), _artifact(spec, 1, 11)]
    for index, other in enumerate(selector.COVERAGE_PRODUCER_SPECS[1:], start=20):
        artifacts.append(_artifact(other, 1, index))

    with pytest.raises(selector.CoverageProducerSelectionError, match="duplicated"):
        selector.select_coverage_producers(
            _arguments(), token="test-token", request=_network(artifacts)
        )


def test_missing_producer_is_rejected_fail_closed() -> None:
    artifacts = [
        _artifact(spec, 1, index + 10)
        for index, spec in enumerate(selector.COVERAGE_PRODUCER_SPECS[:-1])
    ]

    with pytest.raises(selector.CoverageProducerSelectionError, match="missing"):
        selector.select_coverage_producers(
            _arguments(), token="test-token", request=_network(artifacts)
        )


def test_duplicate_identity_across_producer_slots_is_rejected() -> None:
    artifacts = [
        _artifact(
            spec,
            1,
            10 if spec.key in {"backend_shard_0", "backend_shard_1"} else index + 20,
        )
        for index, spec in enumerate(selector.COVERAGE_PRODUCER_SPECS)
    ]

    with pytest.raises(selector.CoverageProducerSelectionError, match="duplicated"):
        selector.select_coverage_producers(
            _arguments(), token="test-token", request=_network(artifacts)
        )


def test_invalid_token_is_rejected_before_network() -> None:
    network = _Network([])

    with pytest.raises(selector.CoverageProducerSelectionError, match="GH_TOKEN"):
        selector.select_coverage_producers(
            _arguments(), token="bad token", request=network
        )
    assert network.requests == []


def test_rust_diagnostic_must_share_coverage_attempt() -> None:
    artifacts = [
        _artifact(spec, 2 if spec.key == "rust_coverage" else 1, index + 10)
        for index, spec in enumerate(selector.COVERAGE_PRODUCER_SPECS)
    ]

    with pytest.raises(selector.CoverageProducerSelectionError, match="Rust"):
        selector.select_coverage_producers(
            _arguments(), token="test-token", request=_network(artifacts)
        )


def test_output_is_atomic_and_preserves_existing_records(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    output.write_text("prior=true\n", encoding="utf-8")
    selector._write_github_output(output, {"example": {"artifact_id": 1}})

    assert output.read_text(encoding="utf-8") == (
        'prior=true\nselections={"example":{"artifact_id":1}}\n'
    )


def test_output_rejects_nonexistent_target(tmp_path: Path) -> None:
    with pytest.raises(selector.CoverageProducerSelectionError, match="existing"):
        selector._write_github_output(tmp_path / "missing", {})
