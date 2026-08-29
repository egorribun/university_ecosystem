from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

import scripts.quality.select_same_run_artifact_cli as selector

REPOSITORY = "example/university-ecosystem"
RUN_ID = "123456789"
CONSUMER_ATTEMPT = "3"
COMMIT_SHA = "a" * 40
EVENT = "pull_request"
WORKFLOW_PATH = ".github/workflows/ci.yml"
PREFIX = "stryker-costs-"
SUFFIX = COMMIT_SHA


class _Network:
    def __init__(self, responses: list[selector.HttpResponse]) -> None:
        self._responses = iter(responses)
        self.requests: list[selector.Request] = []

    def __call__(
        self, request: selector.Request, maximum_bytes: int
    ) -> selector.HttpResponse:
        del maximum_bytes
        self.requests.append(request)
        return next(self._responses)


class _OpenResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self._headers = headers
        self._body = body

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self._headers.items())

    def read(self, _: int) -> bytes:
        return self._body


class _Connection:
    def __init__(self, outcome: _OpenResponse | OSError) -> None:
        self._outcome = outcome
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, target, headers))
        if isinstance(self._outcome, OSError):
            raise self._outcome

    def getresponse(self) -> _OpenResponse:
        assert isinstance(self._outcome, _OpenResponse)
        return self._outcome

    def close(self) -> None:
        self.closed = True


def _response(payload: dict[str, object]) -> selector.HttpResponse:
    return selector.HttpResponse(
        status=200,
        headers={},
        body=json.dumps(payload).encode("utf-8"),
    )


def _arguments() -> selector.SelectionArguments:
    return selector.SelectionArguments(
        repository=REPOSITORY,
        run_id=RUN_ID,
        consumer_run_attempt=CONSUMER_ATTEMPT,
        commit_sha=COMMIT_SHA,
        event=EVENT,
        workflow_path=WORKFLOW_PATH,
        artifact_prefix=PREFIX,
        artifact_suffix=SUFFIX,
        attempt_policy="earlier",
        allow_empty=False,
    )


def _run_metadata() -> dict[str, object]:
    return {
        "id": int(RUN_ID),
        "head_sha": COMMIT_SHA,
        "event": EVENT,
        "path": WORKFLOW_PATH,
        "run_attempt": int(CONSUMER_ATTEMPT),
        "repository": {"full_name": REPOSITORY},
    }


def _artifact(*, artifact_id: int, producer_attempt: int) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": f"{PREFIX}{RUN_ID}-{producer_attempt}-{SUFFIX}",
        "size_in_bytes": 1,
        "expired": False,
        "digest": "sha256:" + "b" * 64,
        "workflow_run": {"id": int(RUN_ID), "head_sha": COMMIT_SHA},
    }


def test_selects_newest_valid_earlier_artifact_and_writes_all_outputs(
    tmp_path: Path,
) -> None:
    github_output = tmp_path / "github-output"
    github_output.write_text("prior=true\n", encoding="utf-8")
    network = _Network(
        [
            _response(_run_metadata()),
            _response(
                {
                    "total_count": 2,
                    "artifacts": [
                        _artifact(artifact_id=10, producer_attempt=1),
                        _artifact(artifact_id=20, producer_attempt=2),
                    ],
                }
            ),
        ]
    )

    result = selector.select_same_run_artifact(
        _arguments(), token="test-token", github_output=github_output, request=network
    )

    assert result == selector.SelectionResult(
        has_candidate=True,
        artifact_id=20,
        artifact_name=f"{PREFIX}{RUN_ID}-2-{SUFFIX}",
        producer_attempt=2,
    )
    assert github_output.read_text(encoding="utf-8") == (
        "prior=true\n"
        "has_candidate=true\n"
        "artifact_id=20\n"
        f"artifact_name={PREFIX}{RUN_ID}-2-{SUFFIX}\n"
        "producer_attempt=2\n"
    )
    assert [request.path for request in network.requests] == [
        f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}",
        f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}/artifacts?per_page=100&page=1",
    ]


def test_paginates_the_current_run_catalog_before_selecting_the_newest_attempt(
    tmp_path: Path,
) -> None:
    github_output = tmp_path / "github-output"
    github_output.write_text("", encoding="utf-8")
    first_page = [_artifact(artifact_id=index + 1, producer_attempt=1) for index in range(1)]
    network = _Network(
        [
            _response(_run_metadata()),
            _response({"total_count": 2, "artifacts": first_page}),
            _response(
                {
                    "total_count": 2,
                    "artifacts": [_artifact(artifact_id=20, producer_attempt=2)],
                }
            ),
        ]
    )

    result = selector.select_same_run_artifact(
        _arguments(), token="test-token", github_output=github_output, request=network
    )

    assert result.producer_attempt == 2
    assert network.requests[-1].path.endswith("page=2")


def test_explicit_attempt_layout_selects_lighthouse_style_same_run_evidence(
    tmp_path: Path,
) -> None:
    github_output = tmp_path / "github-output"
    github_output.write_text("", encoding="utf-8")
    arguments = replace(
        _arguments(),
        artifact_prefix="lighthouse-reports-attempt-",
        artifact_suffix="",
        artifact_name_layout="attempt",
    )
    artifact = _artifact(artifact_id=24, producer_attempt=2)
    artifact["name"] = "lighthouse-reports-attempt-2"
    network = _Network(
        [
            _response(_run_metadata()),
            _response({"total_count": 1, "artifacts": [artifact]}),
        ]
    )

    result = selector.select_same_run_artifact(
        arguments, token="test-token", github_output=github_output, request=network
    )

    assert result == selector.SelectionResult(
        has_candidate=True,
        artifact_id=24,
        artifact_name="lighthouse-reports-attempt-2",
        producer_attempt=2,
    )


def test_candidate_rejects_boolean_workflow_run_identity() -> None:
    arguments = replace(_arguments(), run_id="1", consumer_run_attempt="2")
    artifact = _artifact(artifact_id=4, producer_attempt=1)
    artifact.update(
        {
            "name": f"{PREFIX}1-1-{SUFFIX}",
            "workflow_run": {"id": True, "head_sha": COMMIT_SHA},
        }
    )

    with pytest.raises(selector.SameRunArtifactError, match="foreign workflow"):
        selector._candidate_from_artifact(artifact, arguments)


def test_default_rest_transport_is_single_host_bounded_and_redacts_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection(_OpenResponse(200, {"X-Test": "yes"}, b"{}"))
    monkeypatch.setattr(selector, "HTTPSConnection", lambda *_args, **_kwargs: connection)

    response = selector._default_request(
        selector.Request("/repos/example/repository/actions/runs/1"), 2
    )

    assert response == selector.HttpResponse(200, {"X-Test": "yes"}, b"{}")
    assert connection.requests == [
        ("GET", "/repos/example/repository/actions/runs/1", {})
    ]
    assert connection.closed

    for unsafe_path in ("https://example.invalid", "//example.invalid", "/ok\nheader: x"):
        with pytest.raises(selector.SameRunArtifactError, match="GitHub REST path"):
            selector._default_request(selector.Request(unsafe_path), 2)

    error_connection = _Connection(OSError("token-must-not-appear"))
    monkeypatch.setattr(
        selector, "HTTPSConnection", lambda *_args, **_kwargs: error_connection
    )
    with pytest.raises(selector.SameRunArtifactError) as raised:
        selector._default_request(selector.Request("/repos/example/repository"), 2)
    assert "token-must-not-appear" not in str(raised.value)


def test_catalog_retries_a_concurrent_count_change_until_a_complete_snapshot_converges(
    tmp_path: Path,
) -> None:
    github_output = tmp_path / "github-output"
    github_output.write_text("", encoding="utf-8")
    unrelated = {"name": "unrelated"}
    network = _Network(
        [
            _response(_run_metadata()),
            _response({"total_count": 2, "artifacts": [unrelated]}),
            _response({"total_count": 3, "artifacts": [unrelated]}),
            _response({"total_count": 2, "artifacts": [unrelated]}),
            _response(
                {
                    "total_count": 2,
                    "artifacts": [_artifact(artifact_id=42, producer_attempt=2)],
                }
            ),
        ]
    )

    result = selector.select_same_run_artifact(
        _arguments(), token="test-token", github_output=github_output, request=network
    )

    assert result.artifact_id == 42
    assert [request.path.rsplit("page=", maxsplit=1)[-1] for request in network.requests] == [
        f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}",
        "1",
        "2",
        "1",
        "2",
    ]


def test_output_rejects_hard_links_and_linked_parent_paths(tmp_path: Path) -> None:
    result = selector.SelectionResult(True, 4, "artifact", 1)
    original = tmp_path / "original"
    original.write_text("prior=true\n", encoding="utf-8")
    hard_link = tmp_path / "hard-link"
    try:
        os.link(original, hard_link)
    except OSError as error:
        pytest.skip(f"hard links are unavailable: {error}")
    assert hard_link.stat().st_nlink > 1

    with pytest.raises(selector.SameRunArtifactError, match="hard link"):
        selector._append_output(hard_link, result)

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_parent.symlink_to(real_parent, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    output_through_link = linked_parent / "github-output"
    output_through_link.write_text("", encoding="utf-8")

    with pytest.raises(selector.SameRunArtifactError, match="parent"):
        selector._append_output(output_through_link, result)
