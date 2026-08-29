from __future__ import annotations

import hashlib
import io
import json
import os
import runpy
import stat
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import scripts.quality.download_stryker_cost_artifacts as downloader

API_ROOT = "https://api.github.com"
REPOSITORY = "example/university-ecosystem"
RUN_ID = "123456789"
COMMIT_SHA = "a" * 40
WORKFLOW_PATH = ".github/workflows/ci.yml"
ARTIFACT_PREFIX = "frontend-mutation-historical-costs-"
CDN_URL = "https://pipelines.actions.githubusercontent.com/artifacts/valid?signature=ok"


def _arguments(
    tmp_path: Path, *, consumer_attempt: str = "3"
) -> downloader.DownloadArguments:
    return downloader.DownloadArguments(
        repository=REPOSITORY,
        run_id=RUN_ID,
        consumer_run_attempt=consumer_attempt,
        commit_sha=COMMIT_SHA,
        event="pull_request",
        workflow_path=WORKFLOW_PATH,
        artifact_prefix=ARTIFACT_PREFIX,
        output_root=Path("cost-candidates"),
        github_output=tmp_path / "github-output",
    )


def _response(
    status: int, value: object = b"", headers: Mapping[str, str] | None = None
) -> downloader.HttpResponse:
    body = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
    return downloader.HttpResponse(status=status, headers=headers or {}, body=body)


def _run_metadata(*, run_attempt: int = 3) -> dict[str, object]:
    return {
        "id": int(RUN_ID),
        "head_sha": COMMIT_SHA,
        "event": "pull_request",
        "path": WORKFLOW_PATH,
        "run_attempt": run_attempt,
        "repository": {"full_name": REPOSITORY},
    }


def _zip_payload(
    members: Mapping[str, bytes] | None = None,
    *,
    symlink: bool = False,
) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, value in (
            members or {"HISTORICAL_COSTS.json": b'{"ok":true}\n'}
        ).items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            if symlink:
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(info, value)
    return archive.getvalue()


def _artifact(
    arguments: downloader.DownloadArguments,
    *,
    artifact_id: int,
    attempt: str,
    payload: bytes,
    **overrides: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "id": artifact_id,
        "name": (
            f"{arguments.artifact_prefix}{arguments.run_id}-{attempt}-"
            f"{arguments.commit_sha}"
        ),
        "expired": False,
        "size_in_bytes": len(payload),
        "digest": f"sha256:{hashlib.sha256(payload).hexdigest()}",
        "workflow_run": {"id": int(arguments.run_id), "head_sha": arguments.commit_sha},
    }
    value.update(overrides)
    return value


class _Network:
    def __init__(self, responses: list[downloader.HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str], int]] = []

    def __call__(self, request: Any, maximum_bytes: int) -> downloader.HttpResponse:
        self.calls.append(
            (request.full_url, dict(request.header_items()), maximum_bytes)
        )
        if not self.responses:
            raise AssertionError(f"unexpected request: {request.full_url}")
        return self.responses.pop(0)


def _run_url() -> str:
    return f"{API_ROOT}/repos/{REPOSITORY}/actions/runs/{RUN_ID}"


def _list_url(page: int) -> str:
    return f"{_run_url()}/artifacts?per_page=100&page={page}"


def _archive_url(artifact_id: int) -> str:
    return f"{API_ROOT}/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"


def test_download_selects_latest_earlier_attempt_paginated_and_writes_atomic_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    first_payload = _zip_payload()
    selected_payload = _zip_payload({"HISTORICAL_COSTS.json": b'{"attempt":2}\n'})
    first_page = [
        _artifact(arguments, artifact_id=101, attempt="1", payload=first_payload)
    ] + [{"name": f"unrelated-{index}"} for index in range(99)]
    second_page = [
        _artifact(arguments, artifact_id=202, attempt="2", payload=selected_payload)
    ]
    network = _Network(
        [
            _response(200, _run_metadata()),
            _response(200, {"total_count": 101, "artifacts": first_page}),
            _response(200, {"total_count": 101, "artifacts": second_page}),
            _response(302, headers={"Location": CDN_URL}),
            _response(200, selected_payload),
        ]
    )
    arguments.github_output.write_text("other=value\n", encoding="utf-8")

    result = downloader.download_stryker_cost_artifacts(
        arguments, token="secret-token", request=network
    )

    selected_name = _artifact(
        arguments, artifact_id=202, attempt="2", payload=selected_payload
    )["name"]
    assert result == downloader.DownloadResult(
        has_candidate=True,
        artifact=f"{selected_name}/HISTORICAL_COSTS.json",
    )
    assert (
        tmp_path / arguments.output_root / str(selected_name) / "HISTORICAL_COSTS.json"
    ).read_text(encoding="utf-8") == '{"attempt":2}\n'
    assert arguments.github_output.read_text(encoding="utf-8") == (
        "other=value\n"
        f"artifact={selected_name}/HISTORICAL_COSTS.json\n"
        "has_candidate=true\n"
    )
    assert [call[0] for call in network.calls] == [
        _run_url(),
        _list_url(1),
        _list_url(2),
        _archive_url(202),
        CDN_URL,
    ]
    assert all(
        "Authorization" in dict((key.title(), value) for key, value in call[1].items())
        for call in network.calls[:4]
    )
    assert all(
        key.lower() != "authorization" for key, _ in network.calls[-1][1].items()
    )
    assert network.responses == []


def test_zero_candidates_emits_only_false_output_without_creating_candidate_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    network = _Network(
        [
            _response(200, _run_metadata()),
            _response(200, {"total_count": 1, "artifacts": [{"name": "unrelated"}]}),
        ]
    )

    result = downloader.download_stryker_cost_artifacts(
        arguments, token="secret-token", request=network
    )

    assert result == downloader.DownloadResult(has_candidate=False, artifact=None)
    assert (
        arguments.github_output.read_text(encoding="utf-8") == "has_candidate=false\n"
    )
    assert not (tmp_path / arguments.output_root).exists()
    assert network.responses == []


@pytest.mark.parametrize(
    ("value", "field"),
    [
        (" bad", "value"),
        ("bad\nvalue", "value"),
        (None, "value"),
    ],
)
def test_text_and_decimal_validation_fail_closed(value: object, field: str) -> None:
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._require_text(value, field)
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._require_decimal("0", field)
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._require_decimal("1.5", field)
    assert downloader._require_decimal("42", field) == 42
    assert downloader._is_int(4)
    assert not downloader._is_int(True)


@pytest.mark.parametrize(
    "replacement",
    [
        {"repository": "not-a-repository"},
        {"run_id": "0"},
        {"consumer_run_attempt": "not-a-number"},
        {"commit_sha": "A" * 40},
        {"event": ""},
        {"workflow_path": "workflow.yml"},
        {"artifact_prefix": "../bad-"},
        {"output_root": Path("..")},
    ],
)
def test_arguments_fail_closed_for_untrusted_identity_or_path(
    tmp_path: Path, replacement: dict[str, object]
) -> None:
    arguments = _arguments(tmp_path)
    values = {**arguments.__dict__, **replacement}
    invalid = downloader.DownloadArguments(**values)

    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._validate_arguments(invalid)


@pytest.mark.parametrize("path", [Path(), Path(".."), Path("C:/unsafe")])
def test_safe_relative_directory_rejects_absolute_or_escaping_paths(path: Path) -> None:
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._safe_relative_directory(path)
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._safe_relative_directory(Path("unsafe\x00root"))


class _Reader:
    def __init__(self, value: object) -> None:
        self.value = value

    def read(self, _: int) -> object:
        return self.value


def test_read_limited_rejects_nonbytes_and_oversized_responses() -> None:
    assert downloader._read_limited(_Reader(b"ok"), 2) == b"ok"
    for value in ("not-bytes", b"too-long"):
        with pytest.raises(downloader.ArtifactDownloadError):
            downloader._read_limited(_Reader(value), 2)


class _OpenResponse:
    def __init__(self, status: int, headers: Mapping[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self._body = body

    def read(self, _: int) -> bytes:
        return self._body

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self.headers.items())


class _Connection:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, target, headers))
        if isinstance(self.outcome, BaseException):
            raise self.outcome

    def getresponse(self) -> _OpenResponse:
        assert isinstance(self.outcome, _OpenResponse)
        return self.outcome

    def close(self) -> None:
        self.closed = True


def test_default_request_is_single_hop_bounded_and_handles_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    success = _Connection(_OpenResponse(200, {"X-Test": "yes"}, b"ok"))
    monkeypatch.setattr(
        downloader, "HTTPSConnection", lambda *_args, **_kwargs: success
    )
    response = downloader._default_request(
        downloader.Request("https://example.invalid/path?query=yes"), 2
    )
    assert response == downloader.HttpResponse(200, {"X-Test": "yes"}, b"ok")
    assert success.requests == [("GET", "/path?query=yes", {})]
    assert success.closed

    redirect = _Connection(_OpenResponse(302, {"Location": CDN_URL}, b""))
    monkeypatch.setattr(
        downloader, "HTTPSConnection", lambda *_args, **_kwargs: redirect
    )
    assert downloader._default_request(
        downloader.Request("https://example.invalid"), 2
    ) == (downloader.HttpResponse(302, {"Location": CDN_URL}, b""))

    monkeypatch.setattr(
        downloader,
        "HTTPSConnection",
        lambda *_args, **_kwargs: _Connection(OSError("offline")),
    )
    with pytest.raises(
        downloader.ArtifactDownloadError, match="network request failed"
    ):
        downloader._default_request(downloader.Request("https://example.invalid"), 2)
    with pytest.raises(downloader.ArtifactDownloadError, match="direct HTTPS"):
        downloader._default_request(downloader.Request("http://example.invalid"), 2)
    with pytest.raises(downloader.ArtifactDownloadError, match="malformed"):
        downloader._default_request(
            downloader.Request("https://example.invalid:not-a-port"), 2
        )


def test_default_request_uses_explicit_verified_tls_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection(_OpenResponse(200, {}, b"ok"))
    tls_context = object()
    monkeypatch.setattr(downloader.ssl, "create_default_context", lambda: tls_context)

    def make_connection(*args: object, **kwargs: object) -> _Connection:
        assert args == ("example.invalid",)
        assert kwargs == {"port": 443, "timeout": 20, "context": tls_context}
        return connection

    monkeypatch.setattr(downloader, "HTTPSConnection", make_connection)

    assert downloader._default_request(
        downloader.Request("https://example.invalid"), 2
    ) == downloader.HttpResponse(200, {}, b"ok")
    assert connection.closed


@pytest.mark.parametrize(
    "response",
    [
        _response(500, {}),
        _response(200, b"not-json"),
        _response(200, b"[]"),
        _response(200, b'{"x":1,"x":2}'),
        _response(200, b'{"x":NaN}'),
    ],
)
def test_request_json_fails_closed_on_noncanonical_api_responses(
    response: downloader.HttpResponse,
) -> None:
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._request_json(
            "https://example.invalid", "token", _Network([response])
        )


def test_required_reports_missing_fields() -> None:
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._required({}, "missing")


@pytest.mark.parametrize(
    "field",
    ["id", "head_sha", "event", "path", "run_attempt", "repository"],
)
def test_current_run_metadata_requires_each_exact_trust_boundary(
    tmp_path: Path, field: str
) -> None:
    metadata = _run_metadata()
    metadata[field] = {"full_name": "other/repo"} if field == "repository" else "wrong"
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._validate_current_run(metadata, _arguments(tmp_path))


def test_current_run_metadata_rejects_boolean_numeric_identity_fields(
    tmp_path: Path,
) -> None:
    """Boolean values must not alias integer run identifiers in Python."""

    arguments = replace(_arguments(tmp_path), run_id="1", consumer_run_attempt="1")
    metadata = _run_metadata(run_attempt=1)
    metadata["id"] = True

    with pytest.raises(downloader.ArtifactDownloadError, match="run id"):
        downloader._validate_current_run(metadata, arguments)

    metadata = _run_metadata(run_attempt=1)
    metadata["id"] = 1
    metadata["run_attempt"] = True

    with pytest.raises(downloader.ArtifactDownloadError, match="attempt"):
        downloader._validate_current_run(metadata, arguments)


@pytest.mark.parametrize(
    "response_pages",
    [
        [{"total_count": True, "artifacts": []}],
        [{"total_count": 1, "artifacts": "not-a-list"}],
        [{"total_count": 2, "artifacts": []}],
        [{"total_count": 1, "artifacts": [{"name": "one"}, {"name": "two"}]}],
        [{"total_count": 1, "artifacts": ["not-an-artifact"]}],
        [
            {"total_count": 2, "artifacts": [{"name": "one"}]},
            {"total_count": 3, "artifacts": [{"name": "two"}]},
        ],
    ],
)
def test_list_artifacts_rejects_partial_or_malformed_pagination(
    tmp_path: Path, response_pages: list[dict[str, object]]
) -> None:
    network = _Network([_response(200, page) for page in response_pages])
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._list_artifacts(_arguments(tmp_path), "token", network)


def test_list_artifacts_rejects_exhausting_the_bounded_page_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(downloader, "_MAX_ARTIFACTS", 100)
    network = _Network(
        [
            _response(200, {"total_count": 100, "artifacts": [{"name": "one"}]}),
            _response(200, {"total_count": 100, "artifacts": [{"name": "two"}]}),
        ]
    )
    with pytest.raises(downloader.ArtifactDownloadError, match="maximum page count"):
        downloader._list_artifacts(_arguments(tmp_path), "token", network)


@pytest.mark.parametrize(
    ("overrides", "consumer_attempt"),
    [
        ({"name": f"{ARTIFACT_PREFIX}{RUN_ID}-1-{'b' * 40}"}, "3"),
        ({"id": 0}, "3"),
        ({"size_in_bytes": 0}, "3"),
        ({"expired": True}, "3"),
        ({"digest": "sha256:bad"}, "3"),
        ({"workflow_run": "not-an-object"}, "3"),
        ({"workflow_run": {"id": 99, "head_sha": COMMIT_SHA}}, "3"),
        ({"workflow_run": {"id": int(RUN_ID), "head_sha": "b" * 40}}, "3"),
        ({}, "1"),
    ],
)
def test_candidate_rejects_foreign_expired_malformed_and_future_metadata(
    tmp_path: Path, overrides: dict[str, object], consumer_attempt: str
) -> None:
    arguments = _arguments(tmp_path, consumer_attempt=consumer_attempt)
    payload = _zip_payload()
    artifact = _artifact(
        arguments, artifact_id=17, attempt="1", payload=payload, **overrides
    )
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._candidate_from_artifact(artifact, arguments)


def test_candidate_rejects_boolean_workflow_run_identity(tmp_path: Path) -> None:
    arguments = replace(_arguments(tmp_path), run_id="1", consumer_run_attempt="2")
    payload = _zip_payload()
    artifact = _artifact(
        arguments,
        artifact_id=18,
        attempt="1",
        payload=payload,
        workflow_run={"id": True, "head_sha": COMMIT_SHA},
    )

    with pytest.raises(downloader.ArtifactDownloadError, match="foreign workflow"):
        downloader._candidate_from_artifact(artifact, arguments)


def test_candidate_selection_rejects_duplicate_attempt_or_artifact_id(
    tmp_path: Path,
) -> None:
    arguments = _arguments(tmp_path)
    payload = _zip_payload()
    first = _artifact(arguments, artifact_id=1, attempt="1", payload=payload)
    duplicate_attempt = _artifact(
        arguments, artifact_id=2, attempt="1", payload=payload
    )
    duplicate_id = _artifact(arguments, artifact_id=1, attempt="2", payload=payload)
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._select_candidate([first, duplicate_attempt], arguments)
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._select_candidate([first, duplicate_id], arguments)
    assert downloader._select_candidate([{"name": "unrelated"}], arguments) is None


@pytest.mark.parametrize(
    "location",
    [
        "http://pipelines.actions.githubusercontent.com/a",
        "https://example.invalid/a",
        "https://user@pipelines.actions.githubusercontent.com/a",
        "https://pipelines.actions.githubusercontent.com:444/a",
        "https://pipelines.actions.githubusercontent.com/a#fragment",
        "https://pipelines.actions.githubusercontent.com:bad/a",
    ],
)
def test_redirect_location_requires_trusted_https_cdn(location: str) -> None:
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._validate_cdn_location(location)
    assert downloader._validate_cdn_location(CDN_URL) == CDN_URL


def test_header_requires_exactly_one_nonempty_location() -> None:
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._header({}, "Location")
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._header({"Location": "", "location": CDN_URL}, "Location")


@pytest.mark.parametrize(
    "members,symlink,archive_bytes",
    [
        ({"../HISTORICAL_COSTS.json": b"x"}, False, None),
        ({"HISTORICAL_COSTS.json": b"x", "extra": b"y"}, False, None),
        ({"HISTORICAL_COSTS.json": b"x"}, True, None),
        ({"HISTORICAL_COSTS.json": b"x" * 200_000}, False, None),
        (None, False, b"not-a-zip"),
    ],
)
def test_zip_extraction_rejects_traversal_extra_links_bombs_and_invalid_archives(
    members: Mapping[str, bytes] | None, symlink: bool, archive_bytes: bytes | None
) -> None:
    payload = (
        archive_bytes
        if archive_bytes is not None
        else _zip_payload(members, symlink=symlink)
    )
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._extract_historical_costs(payload)


def test_archive_download_checks_one_redirect_size_and_digest(tmp_path: Path) -> None:
    arguments = _arguments(tmp_path)
    payload = _zip_payload()
    candidate = downloader._candidate_from_artifact(
        _artifact(arguments, artifact_id=7, attempt="1", payload=payload), arguments
    )
    assert candidate is not None
    for responses in (
        [_response(200)],
        [_response(302, headers={"Location": CDN_URL}), _response(500)],
        [_response(302, headers={"Location": CDN_URL}), _response(200, payload + b"x")],
    ):
        with pytest.raises(downloader.ArtifactDownloadError):
            downloader._download_archive(
                candidate, arguments, "token", _Network(responses)
            )
    wrong_digest = downloader._Candidate(
        artifact_id=candidate.artifact_id,
        artifact_name=candidate.artifact_name,
        producer_attempt=candidate.producer_attempt,
        digest="sha256:" + "0" * 64,
        size_in_bytes=len(payload),
    )
    with pytest.raises(downloader.ArtifactDownloadError, match="digest"):
        downloader._download_archive(
            wrong_digest,
            arguments,
            "token",
            _Network(
                [_response(302, headers={"Location": CDN_URL}), _response(200, payload)]
            ),
        )


def test_archive_download_accepts_transport_size_that_differs_from_api_metadata(
    tmp_path: Path,
) -> None:
    """GitHub's logical artifact size is not a transport ZIP length contract."""

    arguments = _arguments(tmp_path)
    payload = _zip_payload()
    candidate = downloader._candidate_from_artifact(
        _artifact(
            arguments,
            artifact_id=8,
            attempt="1",
            payload=payload,
            size_in_bytes=1,
        ),
        arguments,
    )
    assert candidate is not None

    assert (
        downloader._download_archive(
            candidate,
            arguments,
            "token",
            _Network(
                [_response(302, headers={"Location": CDN_URL}), _response(200, payload)]
            ),
        )
        == payload
    )


def test_zip_extraction_rejects_inconsistent_member_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Member:
        filename = "HISTORICAL_COSTS.json"
        external_attr = 0
        flag_bits = 0
        file_size = 3
        compress_size = 3

        def is_dir(self) -> bool:
            return False

    class _Archive:
        def __enter__(self) -> _Archive:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def infolist(self) -> list[_Member]:
            return [_Member()]

        def read(self, _: _Member) -> bytes:
            return b"xx"

    monkeypatch.setattr(downloader.zipfile, "ZipFile", lambda _: _Archive())
    with pytest.raises(downloader.ArtifactDownloadError, match="inconsistent"):
        downloader._extract_historical_costs(b"ignored")


def test_zip_extraction_normalizes_unsupported_member_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Member:
        filename = "HISTORICAL_COSTS.json"
        external_attr = 0
        flag_bits = 0
        file_size = 3
        compress_size = 3

        def is_dir(self) -> bool:
            return False

    class _Archive:
        def __enter__(self) -> _Archive:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def infolist(self) -> list[_Member]:
            return [_Member()]

        def read(self, _: _Member) -> bytes:
            raise NotImplementedError("unsupported compression")

    monkeypatch.setattr(downloader.zipfile, "ZipFile", lambda _: _Archive())

    with pytest.raises(downloader.ArtifactDownloadError, match="cannot be read"):
        downloader._extract_historical_costs(b"ignored")


def test_output_path_and_atomic_cleanup_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._atomic_append_github_output(output, "x=true\n")
    malformed = tmp_path / "malformed"
    malformed.write_text("partial", encoding="utf-8")
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._atomic_append_github_output(malformed, "x=true\n")
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._atomic_append_github_output(
            tmp_path / "missing" / "output", "x=true\n"
        )
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._atomic_append_github_output(tmp_path / "unicode", "\ud800")
    output_file = tmp_path / "github-output"
    output_file.write_text("prior=true\n", encoding="utf-8")
    monkeypatch.setattr(
        downloader.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("boom"))
    )
    with pytest.raises(OSError):
        downloader._atomic_append_github_output(output_file, "x=true\n")
    assert output_file.read_text(encoding="utf-8") == "prior=true\n"
    assert not list(tmp_path.glob(".stryker-output-*"))


def test_output_rejects_hard_links_when_supported(tmp_path: Path) -> None:
    original = tmp_path / "original"
    output = tmp_path / "hard-link"
    original.write_text("prior=true\n", encoding="utf-8")
    os.link(original, output)
    assert output.stat().st_nlink > 1
    with pytest.raises(downloader.ArtifactDownloadError, match="hard link"):
        downloader._assert_safe_output_file(output)


def test_materialization_removes_candidate_when_output_emission_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    payload = _zip_payload()
    candidate = downloader._candidate_from_artifact(
        _artifact(arguments, artifact_id=1, attempt="1", payload=payload), arguments
    )
    assert candidate is not None
    monkeypatch.setattr(
        downloader,
        "_atomic_append_github_output",
        lambda *_: (_ for _ in ()).throw(downloader.ArtifactDownloadError("no output")),
    )
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._materialize_candidate(candidate, b"{}", arguments)
    assert not (tmp_path / arguments.output_root / candidate.artifact_name).exists()
    downloader._remove_materialized_candidate(tmp_path / "does-not-exist")


def test_materialization_rejects_existing_destination_and_cleans_pre_move_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    payload = _zip_payload()
    candidate = downloader._candidate_from_artifact(
        _artifact(arguments, artifact_id=1, attempt="1", payload=payload), arguments
    )
    assert candidate is not None
    root = downloader._safe_output_root(arguments.output_root)
    (root / candidate.artifact_name).mkdir()
    with pytest.raises(downloader.ArtifactDownloadError, match="already exists"):
        downloader._materialize_candidate(candidate, b"{}", arguments)
    (root / candidate.artifact_name).rmdir()
    monkeypatch.setattr(
        downloader.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("cannot move")),
    )
    with pytest.raises(OSError, match="cannot move"):
        downloader._materialize_candidate(candidate, b"{}", arguments)
    assert not (root / candidate.artifact_name).exists()


def test_output_root_and_link_helpers_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    root = downloader._safe_output_root(arguments.output_root)
    assert downloader._safe_output_root(arguments.output_root) == root
    blocked = tmp_path / "blocked"
    blocked.write_text("not-a-directory", encoding="utf-8")
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._safe_output_root(Path("blocked"))
    (tmp_path / "linked").mkdir()
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "linked")
    assert downloader._is_link_or_junction(Path("linked"))
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._safe_output_root(Path("linked"))
    monkeypatch.setattr(downloader, "_is_link_or_junction", lambda _: True)
    with pytest.raises(downloader.ArtifactDownloadError, match="working directory"):
        downloader._safe_output_root(Path("another-root"))


def test_parse_arguments_and_main_never_accept_a_token_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "--repository",
        REPOSITORY,
        "--run-id",
        RUN_ID,
        "--consumer-run-attempt",
        "3",
        "--commit-sha",
        COMMIT_SHA,
        "--event",
        "pull_request",
        "--workflow-path",
        WORKFLOW_PATH,
        "--artifact-prefix",
        ARTIFACT_PREFIX,
        "--output-root",
        "cost-candidates",
        "--github-output",
        str(tmp_path / "github-output"),
    ]
    assert downloader.parse_arguments(argv).repository == REPOSITORY
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert downloader.main(argv) == 1
    assert "GH_TOKEN" in capsys.readouterr().err

    monkeypatch.setenv("GH_TOKEN", "secret-token")
    monkeypatch.setattr(
        downloader, "download_stryker_cost_artifacts", lambda *_args, **_kwargs: None
    )
    assert downloader.main(argv) == 0
    with pytest.raises(SystemExit):
        downloader.parse_arguments([*argv, "--token", "secret-token"])


def test_direct_script_entrypoint_invokes_main_without_project_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", [str(Path(downloader.__file__)), "--help"])
    with pytest.raises(SystemExit) as exit_code:
        runpy.run_path(str(Path(downloader.__file__)), run_name="__main__")
    assert exit_code.value.code == 0
