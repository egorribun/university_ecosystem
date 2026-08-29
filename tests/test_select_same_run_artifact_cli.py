from __future__ import annotations

import json
import os
import runpy
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any, NoReturn, cast

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


class _UrlopenResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self._body = body
        self.closed = False

    def __enter__(self) -> _UrlopenResponse:
        return self

    def __exit__(self, *args: object) -> None:
        del args
        self.closed = True

    def read(self, _: int) -> bytes:
        return self._body


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
    first_page = [
        _artifact(artifact_id=index + 1, producer_attempt=1) for index in range(1)
    ]
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
    transport_response = _UrlopenResponse(200, {"X-Test": "yes"}, b"{}")
    context = ssl.create_default_context()
    calls: list[tuple[urllib.request.Request, ssl.SSLContext, float]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        *,
        context: ssl.SSLContext,
        timeout: float,
    ) -> _UrlopenResponse:
        calls.append((request, context, timeout))
        return transport_response

    monkeypatch.setattr(
        "scripts.quality.select_same_run_artifact_cli.ssl.create_default_context",
        lambda: context,
    )
    monkeypatch.setattr(
        "scripts.quality.select_same_run_artifact_cli.urllib.request.urlopen",
        fake_urlopen,
    )

    result = selector._default_request(
        selector.Request(
            "/repos/example/repository/actions/runs/1", {"Accept": "application/json"}
        ),
        2,
    )

    assert result == selector.HttpResponse(200, {"X-Test": "yes"}, b"{}")
    assert calls[0][0].full_url == (
        "https://api.github.com/repos/example/repository/actions/runs/1"
    )
    assert calls[0][0].get_method() == "GET"
    assert calls[0][0].headers["Accept"] == "application/json"
    assert calls[0][1] is context
    assert calls[0][2] == 20
    assert transport_response.closed

    for unsafe_path in (
        "https://example.invalid",
        "//example.invalid",
        "/ok\nheader: x",
    ):
        with pytest.raises(selector.SameRunArtifactError, match="GitHub REST path"):
            selector._default_request(selector.Request(unsafe_path), 2)

    monkeypatch.setattr(
        "scripts.quality.select_same_run_artifact_cli.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("token-must-not-appear")
        ),
    )
    with pytest.raises(selector.SameRunArtifactError) as raised:
        selector._default_request(selector.Request("/repos/example/repository"), 2)
    assert "token-must-not-appear" not in str(raised.value)


def test_request_json_normalizes_oversized_integer_value_errors() -> None:
    body = b'{"id":' + b"9" * 5000 + b"}"

    with pytest.raises(selector.SameRunArtifactError, match="malformed JSON"):
        selector._request_json(
            "/repos/example/repository/actions/runs/1",
            "test-token",
            lambda request, maximum_bytes: selector.HttpResponse(200, {}, body),
        )


def test_request_json_normalizes_non_bytes_response_bodies() -> None:
    response = selector.HttpResponse(200, {}, cast(bytes, None))

    with pytest.raises(selector.SameRunArtifactError, match="malformed JSON"):
        selector._request_json(
            "/repos/example/repository/actions/runs/1",
            "test-token",
            lambda request, maximum_bytes: response,
        )


def test_default_rest_transport_normalizes_invalid_header_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.quality.select_same_run_artifact_cli.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid header")),
    )

    with pytest.raises(selector.SameRunArtifactError, match="request failed"):
        selector._default_request(
            selector.Request("/repos/example/repository/actions/runs/1"), 2
        )


@pytest.mark.parametrize("token", ["bad\tvalue", "bad\x01value", "bad\u2603value"])
def test_selector_rejects_tokens_that_are_not_safe_http_header_values(
    token: str,
) -> None:
    with pytest.raises(selector.SameRunArtifactError, match=r"header|control"):
        selector.select_same_run_artifact(
            _arguments(),
            token=token,
            github_output=Path("unused-output"),
            request=lambda request, maximum_bytes: _response(_run_metadata()),
        )


def test_selector_rejects_unbounded_run_identifiers() -> None:
    arguments = replace(_arguments(), run_id="1" * 21)

    with pytest.raises(selector.SameRunArtifactError, match="length"):
        selector._validate_arguments(arguments)


def test_output_rejects_unbounded_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    output.write_bytes(b"x" * (selector._MAX_OUTPUT_BYTES + 1))

    with pytest.raises(selector.SameRunArtifactError, match="maximum"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_rejects_symlink_loop_parent(tmp_path: Path) -> None:
    loop = tmp_path / "loop"
    try:
        loop.symlink_to(loop, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")

    with pytest.raises(selector.SameRunArtifactError, match="parent"):
        selector._append_output(
            loop / "github-output", selector.SelectionResult(True, 4, "artifact", 1)
        )


@pytest.mark.parametrize("value", [None, "", " leading", "trailing "])
def test_require_text_rejects_missing_or_untrimmed_values(value: object) -> None:
    with pytest.raises(selector.SameRunArtifactError, match="non-empty"):
        selector._require_text(value, "field")


def test_require_text_rejects_oversized_values() -> None:
    with pytest.raises(selector.SameRunArtifactError, match="maximum length"):
        selector._require_text("x" * (selector._MAX_TEXT_LENGTH + 1), "field")


def test_require_text_rejects_all_control_characters() -> None:
    with pytest.raises(selector.SameRunArtifactError, match="control"):
        selector._require_text("safe\x7fvalue", "field")


@pytest.mark.parametrize("value", ["0", "-1", "1.0", "1 "])
def test_require_decimal_rejects_non_positive_decimal_strings(value: str) -> None:
    with pytest.raises(
        selector.SameRunArtifactError, match=r"positive decimal|non-empty"
    ):
        selector._require_decimal(value, "run_id")


def test_require_decimal_rejects_unbounded_decimal_strings() -> None:
    with pytest.raises(selector.SameRunArtifactError, match="maximum length"):
        selector._require_decimal("1" * (selector._MAX_DECIMAL_DIGITS + 1), "run_id")


def test_read_limited_rejects_invalid_limits_and_streams() -> None:
    with pytest.raises(selector.SameRunArtifactError, match="limit"):
        selector._read_limited(_OpenResponse(200, {}, b""), 0)
    with pytest.raises(selector.SameRunArtifactError, match="malformed"):
        selector._read_limited(object(), 2)


@pytest.mark.parametrize("body", [b"123", "not-bytes"])
def test_read_limited_rejects_oversized_or_non_bytes_bodies(body: object) -> None:
    class _Stream:
        def read(self, _: int) -> object:
            return body

    with pytest.raises(selector.SameRunArtifactError, match="maximum size"):
        selector._read_limited(_Stream(), 2)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "bad repository"),
        ("commit_sha", "A" * 40),
        ("workflow_path", "workflow.yml"),
        ("artifact_prefix", "Bad-"),
        ("artifact_suffix", None),
        ("artifact_suffix", "unsafe suffix"),
        ("artifact_name_layout", "other"),
        ("attempt_policy", "other"),
        ("allow_empty", "true"),
    ],
)
def test_validate_arguments_rejects_unsafe_contract_values(
    field: str, value: object
) -> None:
    arguments = replace(_arguments(), **cast(Any, {field: value}))
    with pytest.raises(selector.SameRunArtifactError):
        selector._validate_arguments(arguments)


def test_validate_arguments_rejects_workflow_path_control_characters() -> None:
    arguments = replace(_arguments(), workflow_path=".github/workflows/ci.yml\x01")
    with pytest.raises(selector.SameRunArtifactError, match="control"):
        selector._validate_arguments(arguments)


def test_json_parser_rejects_duplicate_keys_and_non_finite_constants() -> None:
    duplicate = selector.HttpResponse(200, {}, b'{"a":1,"a":2}')
    constant = selector.HttpResponse(200, {}, b'{"a":NaN}')
    for response, message in ((duplicate, "duplicate"), (constant, "constant")):

        def response_transport(
            request: selector.Request,
            maximum_bytes: int,
            response: selector.HttpResponse = response,
        ) -> selector.HttpResponse:
            del request, maximum_bytes
            return response

        with pytest.raises(selector.SameRunArtifactError, match=message):
            selector._request_json(
                "/repos/example/repository/actions/runs/1",
                "test-token",
                response_transport,
            )


def test_request_json_rejects_non_success_status_and_non_object_json() -> None:
    status = selector.HttpResponse(404, {}, b"{}")
    with pytest.raises(selector.SameRunArtifactError, match="unexpected status"):
        selector._request_json(
            "/repos/example/repository/actions/runs/1",
            "test-token",
            lambda request, maximum_bytes: status,
        )
    with pytest.raises(selector.SameRunArtifactError, match="must be an object"):
        selector._request_json(
            "/repos/example/repository/actions/runs/1",
            "test-token",
            lambda request, maximum_bytes: selector.HttpResponse(200, {}, b"[]"),
        )


def test_required_rejects_missing_fields() -> None:
    with pytest.raises(selector.SameRunArtifactError, match="missing field"):
        selector._required({}, "field")


@pytest.mark.parametrize(
    "field",
    ["head_sha", "event", "path", "run_attempt", "repository"],
)
def test_validate_current_run_rejects_identity_mismatches(field: str) -> None:
    metadata = _run_metadata()
    if field == "run_attempt":
        metadata[field] = int(CONSUMER_ATTEMPT) + 1
    elif field == "repository":
        metadata[field] = {"full_name": "other/repository"}
    else:
        metadata[field] = "mismatched"
    with pytest.raises(selector.SameRunArtifactError):
        selector._validate_current_run(metadata, _arguments())


@pytest.mark.parametrize("field", ["id", "run_attempt"])
def test_validate_current_run_rejects_boolean_numeric_identity(field: str) -> None:
    metadata = _run_metadata()
    metadata[field] = True
    with pytest.raises(selector.SameRunArtifactError, match="current"):
        selector._validate_current_run(metadata, _arguments())


def test_validate_current_run_rejects_malformed_repository_identity() -> None:
    metadata = _run_metadata()
    metadata["repository"] = None
    with pytest.raises(selector.SameRunArtifactError, match="repository"):
        selector._validate_current_run(metadata, _arguments())


def test_validate_current_run_rejects_mismatched_run_id() -> None:
    metadata = _run_metadata()
    metadata["id"] = int(RUN_ID) + 1
    with pytest.raises(selector.SameRunArtifactError, match="current run"):
        selector._validate_current_run(metadata, _arguments())


@pytest.mark.parametrize(
    "mutations",
    [
        {"name": f"{PREFIX}invalid"},
        {"id": 0},
        {"size_in_bytes": 0},
        {"expired": True},
        {"digest": "bad"},
        {"workflow_run": None},
        {"workflow_run": {"id": int(RUN_ID), "head_sha": "other"}},
    ],
)
def test_candidate_rejects_malformed_provenance_fields(
    mutations: dict[str, object],
) -> None:
    artifact = _artifact(artifact_id=10, producer_attempt=1)
    if "workflow_run" in mutations and isinstance(mutations["workflow_run"], dict):
        artifact["workflow_run"] = mutations["workflow_run"]
    else:
        artifact.update(mutations)
    with pytest.raises(selector.SameRunArtifactError):
        selector._candidate_from_artifact(artifact, _arguments())


def test_candidate_rejects_foreign_workflow_run() -> None:
    artifact = _artifact(artifact_id=10, producer_attempt=1)
    artifact["workflow_run"] = {"id": int(RUN_ID) + 1, "head_sha": COMMIT_SHA}
    with pytest.raises(selector.SameRunArtifactError, match="foreign workflow"):
        selector._candidate_from_artifact(artifact, _arguments())


def test_candidate_rejects_future_attempt_and_skips_current_earlier_attempt() -> None:
    future = _artifact(artifact_id=10, producer_attempt=int(CONSUMER_ATTEMPT) + 1)
    with pytest.raises(selector.SameRunArtifactError, match="future"):
        selector._candidate_from_artifact(future, _arguments())
    current = _artifact(artifact_id=10, producer_attempt=int(CONSUMER_ATTEMPT))
    assert selector._candidate_from_artifact(current, _arguments()) is None


def test_select_candidate_rejects_duplicate_attempts_and_ids() -> None:
    first = _artifact(artifact_id=10, producer_attempt=1)
    same_attempt = _artifact(artifact_id=11, producer_attempt=1)
    with pytest.raises(selector.SameRunArtifactError, match="duplicated"):
        selector._select_candidate([first, same_attempt], _arguments())
    same_id = _artifact(artifact_id=10, producer_attempt=2)
    with pytest.raises(selector.SameRunArtifactError, match="duplicated"):
        selector._select_candidate([first, same_id], _arguments())
    assert selector._select_candidate([], _arguments()) is None


def test_default_transport_rejects_invalid_status_and_bounded_body_errors() -> None:
    response = _UrlopenResponse(200, {}, b"abc")
    response.status = cast(int, "bad")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "scripts.quality.select_same_run_artifact_cli.urllib.request.urlopen",
            lambda *_args, **_kwargs: response,
        )
        with pytest.raises(selector.SameRunArtifactError, match="invalid status"):
            selector._default_request(
                selector.Request("/repos/example/repository/actions/runs/1"), 2
            )

    response = _UrlopenResponse(200, {}, b"abc")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "scripts.quality.select_same_run_artifact_cli.urllib.request.urlopen",
            lambda *_args, **_kwargs: response,
        )
        with pytest.raises(selector.SameRunArtifactError, match="maximum size"):
            selector._default_request(
                selector.Request("/repos/example/repository/actions/runs/1"), 2
            )


@pytest.mark.parametrize(
    "error",
    [urllib.error.URLError("network failure"), UnicodeError("decode failure")],
)
def test_default_transport_normalizes_url_and_unicode_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def raise_error(*_args: object, **_kwargs: object) -> NoReturn:
        raise error

    monkeypatch.setattr(
        "scripts.quality.select_same_run_artifact_cli.urllib.request.urlopen",
        raise_error,
    )
    with pytest.raises(selector.SameRunArtifactError, match="request failed"):
        selector._default_request(
            selector.Request("/repos/example/repository/actions/runs/1"), 2
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"total_count": True, "artifacts": []},
        {"total_count": -1, "artifacts": []},
        {"total_count": selector._MAX_ARTIFACTS + 1, "artifacts": []},
        {"total_count": 0, "artifacts": {}},
    ],
)
def test_catalog_snapshot_rejects_malformed_listing(payload: dict[str, object]) -> None:
    with pytest.raises(selector.SameRunArtifactError, match="listing"):
        selector._list_artifact_snapshot(
            _arguments(),
            "test-token",
            lambda request, maximum_bytes: _response(payload),
        )


def test_catalog_snapshot_rejects_count_overflow_and_malformed_artifact() -> None:
    with pytest.raises(selector._CatalogChanged):
        selector._list_artifact_snapshot(
            _arguments(),
            "test-token",
            lambda request, maximum_bytes: _response(
                {"total_count": 0, "artifacts": [{}]}
            ),
        )
    with pytest.raises(selector.SameRunArtifactError, match="malformed artifact"):
        selector._list_artifact_snapshot(
            _arguments(),
            "test-token",
            lambda request, maximum_bytes: _response(
                {"total_count": 1, "artifacts": [None]}
            ),
        )


def test_catalog_snapshot_retries_empty_page_and_exhausts_page_bound() -> None:
    with pytest.raises(selector._CatalogChanged):
        selector._list_artifact_snapshot(
            _arguments(),
            "test-token",
            lambda request, maximum_bytes: _response(
                {"total_count": 1, "artifacts": []}
            ),
        )

    responses = iter(
        _response(
            {
                "total_count": selector._MAX_ARTIFACTS,
                "artifacts": [{} for _ in range(99)],
            }
        )
        for _ in range((selector._MAX_ARTIFACTS // selector._ARTIFACT_PAGE_SIZE) + 1)
    )
    with pytest.raises(selector._CatalogChanged):
        selector._list_artifact_snapshot(
            _arguments(), "test-token", lambda request, maximum_bytes: next(responses)
        )


def test_list_artifacts_fails_closed_after_catalog_never_converges() -> None:
    with pytest.raises(selector.SameRunArtifactError, match="converge"):
        selector._list_artifacts(
            _arguments(),
            "test-token",
            lambda request, maximum_bytes: _response(
                {"total_count": 1, "artifacts": []}
            ),
        )


def test_output_parent_and_file_validators_reject_missing_non_directory_and_links(
    tmp_path: Path,
) -> None:
    with pytest.raises(selector.SameRunArtifactError, match="available"):
        selector._safe_output_parent(tmp_path / "missing" / "github-output")
    parent_file = tmp_path / "parent-file"
    parent_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(selector.SameRunArtifactError, match="regular directory"):
        selector._safe_output_parent(parent_file / "github-output")

    with pytest.raises(selector.SameRunArtifactError, match="existing"):
        selector._safe_output_file(tmp_path / "missing-output")
    with pytest.raises(selector.SameRunArtifactError, match="regular file"):
        selector._safe_output_file(tmp_path)
    target = tmp_path / "target-output"
    target.write_text("", encoding="utf-8")
    linked = tmp_path / "linked-output"
    try:
        linked.symlink_to(target)
    except OSError as error:
        pytest.skip(f"file symlinks are unavailable: {error}")
    with pytest.raises(selector.SameRunArtifactError, match="link"):
        selector._safe_output_file(linked)


def test_output_append_rejects_parent_inspection_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    original_lstat = Path.lstat

    def failing_lstat(path: Path) -> os.stat_result:
        if path == tmp_path:
            raise OSError("parent unavailable")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", failing_lstat)
    with pytest.raises(selector.SameRunArtifactError, match="inspected"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_append_rejects_parent_that_becomes_non_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    parent_file = tmp_path / "parent-file"
    parent_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(selector, "_safe_output_parent", lambda path: parent_file)
    with pytest.raises(selector.SameRunArtifactError, match="regular directory"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_append_normalizes_read_and_identity_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")

    def failing_open(path: Path, *args: object, **kwargs: object) -> NoReturn:
        del path, args, kwargs
        raise OSError("read failed")

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(selector.SameRunArtifactError, match="cannot be read"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )

    monkeypatch.undo()
    monkeypatch.setattr(selector, "_same_file_identity", lambda before, after: False)
    with pytest.raises(selector.SameRunArtifactError, match="changed while"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_append_rejects_incomplete_prior_record(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    output.write_text("prior=true", encoding="utf-8")
    with pytest.raises(selector.SameRunArtifactError, match="incomplete"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_append_normalizes_atomic_prepare_and_replace_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.quality.select_same_run_artifact_cli.tempfile.mkstemp",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("mkstemp failed")),
    )
    with pytest.raises(selector.SameRunArtifactError, match="prepared"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )

    monkeypatch.undo()
    monkeypatch.setattr(
        "scripts.quality.select_same_run_artifact_cli.os.replace",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("replace failed")),
    )
    with pytest.raises(selector.SameRunArtifactError, match="written"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_append_detects_pre_replace_identity_and_parent_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    calls = 0

    def identity_changes(before: os.stat_result, after: os.stat_result) -> bool:
        nonlocal calls
        calls += 1
        return calls == 1

    monkeypatch.setattr(selector, "_same_file_identity", identity_changes)
    with pytest.raises(selector.SameRunArtifactError, match="before replacement"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )

    monkeypatch.undo()
    other_parent = tmp_path / "other-parent"
    other_parent.mkdir()
    parents = iter((tmp_path, other_parent))
    monkeypatch.setattr(selector, "_safe_output_parent", lambda path: next(parents))
    with pytest.raises(selector.SameRunArtifactError, match="parent changed"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_append_detects_parent_stat_and_identity_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    original_lstat = Path.lstat
    calls = 0

    def failing_second_parent_lstat(path: Path) -> os.stat_result:
        nonlocal calls
        if path == tmp_path:
            calls += 1
            if calls == 2:
                raise OSError("parent changed")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", failing_second_parent_lstat)
    with pytest.raises(selector.SameRunArtifactError, match="parent changed"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )

    monkeypatch.undo()
    other_parent = tmp_path / "other-parent"
    other_parent.mkdir()
    calls = 0

    def changed_parent_lstat(path: Path) -> os.stat_result:
        nonlocal calls
        if path == tmp_path:
            calls += 1
            if calls == 2:
                return original_lstat(other_parent)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", changed_parent_lstat)
    with pytest.raises(selector.SameRunArtifactError, match="parent changed"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_append_normalizes_temporary_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.quality.select_same_run_artifact_cli.os.replace",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("replace failed")),
    )

    def failing_unlink(path: Path, *, missing_ok: bool = False) -> NoReturn:
        del path, missing_ok
        raise OSError("cleanup failed")

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    with pytest.raises(selector.SameRunArtifactError, match="cleanup"):
        selector._append_output(
            output, selector.SelectionResult(True, 4, "artifact", 1)
        )


def test_output_parent_rejects_ancestor_symlink_traversal(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    child = real_root / "child"
    child.mkdir()
    linked_root = tmp_path / "linked-root"
    try:
        linked_root.symlink_to(real_root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    with pytest.raises(selector.SameRunArtifactError, match="traverse"):
        selector._safe_output_parent(linked_root / "child" / "github-output")


def test_select_artifact_fails_when_empty_candidates_are_not_allowed(
    tmp_path: Path,
) -> None:
    network = _Network(
        [
            _response(_run_metadata()),
            _response({"total_count": 1, "artifacts": [{"name": "unrelated"}]}),
        ]
    )
    with pytest.raises(selector.SameRunArtifactError, match="no valid"):
        selector.select_same_run_artifact(
            _arguments(),
            token="test-token",
            github_output=tmp_path / "github-output",
            request=network,
        )


def test_select_artifact_emits_empty_result_when_allowed(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    network = _Network(
        [
            _response(_run_metadata()),
            _response({"total_count": 1, "artifacts": [{"name": "unrelated"}]}),
        ]
    )
    result = selector.select_same_run_artifact(
        replace(_arguments(), allow_empty=True),
        token="test-token",
        github_output=output,
        request=network,
    )
    assert result == selector.SelectionResult(False, None, None, None)
    assert output.read_text(encoding="utf-8") == (
        "has_candidate=false\nartifact_id=\nartifact_name=\nproducer_attempt=\n"
    )


def test_select_artifact_enforces_total_request_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    monkeypatch.setattr(selector, "_MAX_REQUESTS_PER_SELECTION", 0)
    with pytest.raises(selector.SameRunArtifactError, match="request budget"):
        selector.select_same_run_artifact(
            _arguments(),
            token="test-token",
            github_output=output,
            request=lambda request, maximum_bytes: _response(_run_metadata()),
        )


def test_parse_arguments_builds_trusted_selection_arguments() -> None:
    arguments = selector.parse_arguments(
        [
            "--repository",
            REPOSITORY,
            "--run-id",
            RUN_ID,
            "--consumer-run-attempt",
            CONSUMER_ATTEMPT,
            "--commit-sha",
            COMMIT_SHA,
            "--event",
            EVENT,
            "--workflow-path",
            WORKFLOW_PATH,
            "--artifact-prefix",
            PREFIX,
            "--artifact-suffix",
            SUFFIX,
            "--artifact-name-layout",
            "attempt",
            "--attempt-policy",
            "current-or-earlier",
            "--allow-empty",
        ]
    )
    assert arguments == selector.SelectionArguments(
        repository=REPOSITORY,
        run_id=RUN_ID,
        consumer_run_attempt=CONSUMER_ATTEMPT,
        commit_sha=COMMIT_SHA,
        event=EVENT,
        workflow_path=WORKFLOW_PATH,
        artifact_prefix=PREFIX,
        artifact_suffix=SUFFIX,
        attempt_policy="current-or-earlier",
        allow_empty=True,
        artifact_name_layout="attempt",
    )


def test_main_returns_success_when_selection_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(selector, "parse_arguments", lambda argv: _arguments())
    monkeypatch.setattr(
        selector,
        "select_same_run_artifact",
        lambda arguments, *, token, github_output, request: selector.SelectionResult(
            True, 4, "artifact", 1
        ),
    )
    assert selector.main([]) == 0


def test_main_returns_failure_and_redacts_same_run_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        selector,
        "parse_arguments",
        lambda argv: (_ for _ in ()).throw(
            selector.SameRunArtifactError("secret-token-must-not-leak")
        ),
    )
    assert selector.main([]) == 1
    assert "secret-token-must-not-leak" in capsys.readouterr().err


def test_module_entrypoint_exits_fail_closed_without_github_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "select_same_run_artifact_cli.py",
            "--repository",
            REPOSITORY,
            "--run-id",
            RUN_ID,
            "--consumer-run-attempt",
            CONSUMER_ATTEMPT,
            "--commit-sha",
            COMMIT_SHA,
            "--event",
            EVENT,
            "--workflow-path",
            WORKFLOW_PATH,
            "--artifact-prefix",
            PREFIX,
            "--artifact-suffix",
            SUFFIX,
            "--attempt-policy",
            "earlier",
        ],
    )
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(selector.__file__), run_name="__main__")
    assert raised.value.code == 1


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
    assert [
        request.path.rsplit("page=", maxsplit=1)[-1] for request in network.requests
    ] == [
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
