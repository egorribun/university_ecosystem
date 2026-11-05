"""Fail-closed tests for the SQLMap completion and injection gate (AUD-381)."""

from __future__ import annotations

import copy
import json
import os
import re
import runpy
import shlex
import sys
from pathlib import Path

import pytest
import yaml

from scripts.quality import sqlmap_scan_gate as gate

_START = b"[*] starting @ 10:00:00 /2026-11-04/\n"
_END = b"\n[*] ending @ 10:00:09 /2026-11-04/\n\n"
_INJECTION = (
    b"sqlmap identified the following injection point(s) with a total of 12 HTTP(s) "
    b"requests\n"
)
_TARGETS = (
    b"[10:00:00] [INFO] derived 1 target(s) from the OpenAPI/Swagger specification\n"
)
_TESTED_PARAMETER = (
    b"[10:00:05] [WARNING] GET parameter 'limit' does not seem to be injectable\n"
    b"[10:00:06] [WARNING] GET parameter 'cursor' does not seem to be injectable\n"
    b"[10:00:07] [WARNING] (custom) HEADER parameter 'if-none-match #1*' "
    b"does not seem to be injectable\n"
)
_SCAN_DONE = (
    b"[10:00:08] [INFO] you can find results of scanning in multiple targets mode "
    b"inside the CSV file 'sqlmap-output/results.csv'\n"
)
_CSV_HEADER = b"Target URL,Place,Parameter,Technique(s),Note(s)\n"
_CLEAN_RUN = _START + _TARGETS + _TESTED_PARAMETER + _SCAN_DONE + _END


def test_scope_uses_real_news_get_operation_only() -> None:
    get = {
        "operationId": "news_list_api_v1_news_get",
        "parameters": [
            {"name": "limit", "in": "query", "schema": {"type": "integer"}},
            {"name": "cursor", "in": "query"},
            {"name": "if-none-match", "in": "header"},
        ],
    }
    source = {
        "openapi": "3.1.0",
        "paths": {
            "/api/v1/news": {"get": get, "post": {}},
            "/api/v1/other": {"get": {}},
        },
        "components": {},
    }

    scoped = gate.scope_openapi(source)

    assert scoped["servers"] == [{"url": "http://127.0.0.1:8000"}]
    assert scoped["paths"]["/api/v1/news"]["get"]["parameters"] == get["parameters"]
    assert scoped["paths"]["/api/v1/news"]["get"]["operationId"] == get["operationId"]
    assert scoped["x-sqlmap-scope"] == {
        "version": 1,
        "operations": [{"method": "GET", "path": "/api/v1/news"}],
    }
    assert source["paths"]["/api/v1/news"]["post"] == {}


def _scope_fixture() -> dict[str, object]:
    return {
        "openapi": "3.1.0",
        "paths": {
            "/api/v1/news": {
                "get": {
                    "operationId": "news_list_api_v1_news_get",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                        {"name": "cursor", "in": "query", "schema": {"type": "string"}},
                        {
                            "name": "if-none-match",
                            "in": "header",
                            "schema": {"type": "string"},
                        },
                    ],
                }
            }
        },
    }


def test_scope_discards_all_openapi_destination_overrides() -> None:
    source = _scope_fixture()
    source.update(
        servers=[{"url": "https://attacker.invalid"}],
        host="attacker.invalid",
        basePath="/outside",
        schemes=["https"],
        components={
            "schemas": {"Other": {"servers": [{"url": "https://attacker.invalid"}]}}
        },
    )
    paths = source["paths"]
    assert isinstance(paths, dict)
    path_item = paths["/api/v1/news"]
    path_item["servers"] = [{"url": "https://path.attacker.invalid"}]
    path_item["get"]["servers"] = [{"url": "https://operation.attacker.invalid"}]
    before = copy.deepcopy(source)

    scoped = gate.scope_openapi(source)

    assert scoped["servers"] == [{"url": "http://127.0.0.1:8000"}]
    assert "attacker.invalid" not in json.dumps(scoped)
    assert not {"host", "basePath", "schemes", "components"} & scoped.keys()
    assert "servers" not in scoped["paths"]["/api/v1/news"]["get"]
    assert source == before


@pytest.mark.parametrize(
    "mutation",
    [
        "swagger",
        "mixed_version",
        "missing_version",
        "unsupported_version",
        "path_ref",
        "operation_ref",
        "path_parameters",
        "body",
        "parameter_ref",
        "nested_ref",
    ],
)
def test_scope_rejects_unsupported_forms_that_could_hide_targets_or_inputs(
    mutation: str,
) -> None:
    source = _scope_fixture()
    paths = source["paths"]
    assert isinstance(paths, dict)
    path_item = paths["/api/v1/news"]
    operation = path_item["get"]
    if mutation == "swagger":
        source.pop("openapi")
        source.update(swagger="2.0", host="attacker.invalid", schemes=["https"])
    elif mutation == "mixed_version":
        source["swagger"] = "2.0"
    elif mutation == "missing_version":
        source.pop("openapi")
    elif mutation == "unsupported_version":
        source["openapi"] = "4.0.0"
    elif mutation == "path_ref":
        path_item["$ref"] = "#/components/pathItems/other"
    elif mutation == "operation_ref":
        operation["$ref"] = "#/components/operations/other"
    elif mutation == "path_parameters":
        path_item["parameters"] = [{"name": "extra", "in": "query"}]
    elif mutation == "body":
        operation["requestBody"] = {"content": {"application/json": {}}}
    elif mutation == "parameter_ref":
        operation["parameters"][0]["$ref"] = "https://attacker.invalid/parameter"
    else:
        operation["parameters"][0]["schema"]["$ref"] = "#/components/schemas/Remote"

    with pytest.raises(gate.ScanEvidenceError):
        gate.scope_openapi(source)


def test_workflow_disables_redirects_and_anchors_exact_loopback_scope() -> None:
    path = Path(gate.__file__).resolve().parents[2] / ".github/workflows/sqlmap.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["sqlmap"]["steps"]
    scan = next(step for step in steps if step["name"] == "Run SQLMap Scan on API")
    script = scan["run"]
    assert (
        "unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY all_proxy ALL_PROXY"
        in script
    )
    invocation = script[script.index("uv run sqlmap") :].split(
        "> sqlmap-output/scan-console.log", 1
    )[0]
    arguments = shlex.split(invocation.replace("\\\n", ""), comments=True)
    assert "--ignore-redirects" in arguments
    assert "--answers=refresh=N" in arguments
    assert not any(
        argument == "--http2" or argument.startswith("--http2=")
        for argument in arguments
    )
    assert (
        "--headers=Accept-Encoding: identity\\nX-Request-ID: sqlmap-aud-381"
        in arguments
    )
    scopes = [
        argument.removeprefix("--scope=")
        for argument in arguments
        if argument.startswith("--scope=")
    ]
    assert len(scopes) == 1
    pattern = scopes[0]
    assert re.search(pattern, "http://127.0.0.1:8000/api/v1/news?limit=1")
    for outside in (
        "http://attacker.invalid/api/v1/news?limit=1",
        "http://127.0.0.1:8000.attacker.invalid/api/v1/news?limit=1",
        "http://127.0.0.1:8000@attacker.invalid/api/v1/news?limit=1",
        "http://user@127.0.0.1:8000/api/v1/news?limit=1",
        "http://127.0.0.1:8001/api/v1/news?limit=1",
        "http://127.0.0.1:8000/api/v1/news-extra?limit=1",
        "http://localhost:8000/api/v1/news?limit=1",
    ):
        assert re.search(pattern, outside) is None


def test_workflow_retains_only_sanitized_count_receipt() -> None:
    path = Path(gate.__file__).resolve().parents[2] / ".github/workflows/sqlmap.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = {step["name"]: step for step in workflow["jobs"]["sqlmap"]["steps"]}
    scan = steps["Run SQLMap Scan on API"]
    startup = steps["Start FastAPI Backend in Background"]
    publish = steps["Publish sanitized SQLMap evidence"]
    upload = steps["Upload SQLMap result logs"]
    assert "> sqlmap-output/scan-console.log 2>&1" in scan["run"]
    assert "| tee" not in scan["run"]
    assert 'request_id_ctx.get() == "sqlmap-aud-381"' in startup["run"]
    assert (
        "unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY all_proxy ALL_PROXY"
        in startup["run"]
    )
    assert publish["if"] == "${{ always() }}"
    assert "sqlmap_scan_gate.py publish-evidence" in publish["run"]
    assert upload["with"]["path"] == "sqlmap-evidence/receipt.json"
    assert upload["with"]["retention-days"] == 90
    assert upload["with"]["if-no-files-found"] == "error"


@pytest.mark.parametrize(
    "source",
    [
        None,
        {},
        {"openapi": "3.1.0", "paths": {}},
        {
            "openapi": "3.1.0",
            "paths": {"/api/v1/news": {"get": {"operationId": "changed"}}},
        },
        {
            "openapi": "3.1.0",
            "paths": {
                "/api/v1/news": {"get": {"operationId": "news_list_api_v1_news_get"}}
            },
        },
    ],
)
def test_scope_rejects_missing_or_changed_operation(source: object) -> None:
    with pytest.raises(gate.ScanEvidenceError):
        gate.scope_openapi(source)


@pytest.mark.parametrize(
    "parameters",
    [
        [{"in": "query", "name": "limit"}] * 3,
        [{"in": "query", "name": "limit"}, {"in": "query", "name": "cursor"}],
        [
            {"in": [], "name": "limit"},
            {"in": "query", "name": "cursor"},
            {"in": "header", "name": "if-none-match"},
        ],
        [
            {"in": "query", "name": []},
            {"in": "query", "name": "cursor"},
            {"in": "header", "name": "if-none-match"},
        ],
        [
            {"in": "query", "name": "unexpected"},
            {"in": "query", "name": "cursor"},
            {"in": "header", "name": "if-none-match"},
        ],
    ],
)
def test_scope_rejects_changed_or_duplicate_parameters(
    parameters: list[object],
) -> None:
    source = {
        "openapi": "3.1.0",
        "paths": {
            "/api/v1/news": {
                "get": {
                    "operationId": "news_list_api_v1_news_get",
                    "parameters": parameters,
                }
            }
        },
    }
    with pytest.raises(gate.ScanEvidenceError):
        gate.scope_openapi(source)


def test_scope_command_writes_versioned_scope_from_real_schema(
    tmp_path: Path, app
) -> None:
    source = tmp_path / "source.json"
    output = tmp_path / "scope.json"
    source.write_text(json.dumps(app.openapi()), encoding="utf-8")

    assert gate.main(["scope-openapi", str(source), str(output)]) == 0
    scoped = json.loads(output.read_text(encoding="utf-8"))
    assert list(scoped["paths"]) == ["/api/v1/news"]
    assert list(scoped["paths"]["/api/v1/news"]) == ["get"]
    assert scoped["x-sqlmap-scope"]["version"] == 1


@pytest.mark.parametrize("contents", [None, "{not-json}", "{}"])
def test_scope_command_rejects_missing_or_invalid_source(
    tmp_path: Path, contents: str | None
) -> None:
    source = tmp_path / "source.json"
    output = tmp_path / "scope.json"
    if contents is not None:
        source.write_text(contents, encoding="utf-8")

    assert gate.main(["scope-openapi", str(source), str(output)]) == 1
    assert not output.exists()


@pytest.mark.asyncio
async def test_admitted_operation_executes_real_pagination_queries(
    async_client, db_session, assert_max_queries
) -> None:
    from app.models import News

    db_session.add_all(
        [
            News(title="SQLMap seed one", content="First article"),
            News(title="SQLMap seed two", content="Second article"),
        ]
    )
    await db_session.commit()

    async with assert_max_queries(10) as statements:
        first = await async_client.get("/news", params={"limit": 1})
        second = await async_client.get("/news", params={"limit": 2})

    assert first.status_code == second.status_code == 200
    assert len(first.json()["items"]) == 1
    assert len(second.json()["items"]) == 2
    assert any("FROM news" in statement for statement in statements)


def _layout(
    tmp_path: Path,
    console: bytes | None,
    result_log: bytes | None = b"log content\n",
    csv: bytes | None = _CSV_HEADER,
) -> tuple[Path, Path]:
    """Create the output directory and console log exactly as the workflow does."""

    output_dir = tmp_path / "sqlmap-output"
    host_dir = output_dir / "api.invalid"
    host_dir.mkdir(parents=True)
    if result_log is not None:
        (host_dir / "log").write_bytes(result_log)
    if csv is not None:
        (output_dir / "results.csv").write_bytes(csv)
    (output_dir / "db-query-evidence.log").write_bytes(b"SQLMAP SELECT news\n")
    console_log = output_dir / "scan-console.log"
    if console is not None:
        console_log.write_bytes(console)
    return output_dir, console_log


def _run(
    tmp_path: Path,
    outcome: str,
    console: bytes | None,
    result_log: bytes | None = b"log content\n",
    summary: bool = False,
) -> int:
    output_dir, console_log = _layout(tmp_path, console, result_log)
    summary_path = tmp_path / "summary.md" if summary else None
    return gate.run_gate(outcome, output_dir, console_log, summary_path)


def test_completed_clean_scan_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(tmp_path, "success", _CLEAN_RUN)

    assert code == 0
    assert "SQLMap completed and reported no confirmed injection points." in (
        capsys.readouterr().out
    )


def test_completed_scan_with_confirmed_injection_fails_and_names_the_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(tmp_path, "success", _CLEAN_RUN + _INJECTION)

    assert code == 1
    err = capsys.readouterr().err
    assert "SQLMap confirmed SQL injection." in err
    assert "sanitized SQLMap evidence receipt" in err


def test_injection_recorded_only_in_the_result_log_fails(tmp_path: Path) -> None:
    code = _run(
        tmp_path,
        "success",
        _CLEAN_RUN,
        result_log=_INJECTION,
    )

    assert code == 1


def test_resumed_injection_from_a_stored_session_also_fails(tmp_path: Path) -> None:
    code = _run(
        tmp_path,
        "success",
        _CLEAN_RUN
        + b"sqlmap resumed the following injection point(s) from stored session\n",
    )

    assert code == 1


def _run_with_csv(tmp_path: Path, console: bytes, csv: bytes | None) -> int:
    output_dir, console_log = _layout(tmp_path, console, csv=csv)
    return gate.run_gate("success", output_dir, console_log, None)


def test_finally_banner_alone_does_not_prove_target_loop_completed(
    tmp_path: Path,
) -> None:
    console = _START + _TARGETS + _TESTED_PARAMETER + _END
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_incomplete_target_errors_fail_even_after_target_loop_finishes(
    tmp_path: Path,
) -> None:
    console = (
        _START
        + _TARGETS
        + _TESTED_PARAMETER
        + b"[10:00:06] [ERROR] connection refused, skipping to the next target\n"
        + _SCAN_DONE
        + _END
    )
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_only_one_admitted_parameter_tested_fails_closed(tmp_path: Path) -> None:
    console = (
        _START
        + _TARGETS
        + b"[10:00:05] [WARNING] GET parameter 'limit' does not seem to be injectable\n"
        + _SCAN_DONE
        + _END
    )
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_parameter_results_after_target_loop_do_not_prove_scan(tmp_path: Path) -> None:
    console = _START + _TARGETS + _SCAN_DONE + _TESTED_PARAMETER + _END
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_unexpected_multiple_openapi_targets_fail_closed(tmp_path: Path) -> None:
    console = _CLEAN_RUN.replace(b"derived 1 target(s)", b"derived 2 target(s)")
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_aborted_target_fails_even_if_target_loop_finishes(tmp_path: Path) -> None:
    console = (
        _START
        + _TARGETS
        + _TESTED_PARAMETER
        + b"[10:00:06] [WARNING] user aborted during detection phase\n"
        + _SCAN_DONE
        + _END
    )
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_no_tested_parameter_fails_even_if_target_loop_finishes(tmp_path: Path) -> None:
    console = _START + _TARGETS + _SCAN_DONE + _END
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_missing_csv_fails_even_if_target_loop_finishes(tmp_path: Path) -> None:
    console = _START + _TARGETS + _TESTED_PARAMETER + _SCAN_DONE + _END
    assert _run_with_csv(tmp_path, console, None) == 1


@pytest.mark.parametrize("evidence", [None, b"", b"other query\n", b"SELECT news\n"])
def test_completed_scan_without_database_query_evidence_fails(
    tmp_path: Path, evidence: bytes | None
) -> None:
    output_dir, console_log = _layout(tmp_path, _CLEAN_RUN)
    query_log = output_dir / "db-query-evidence.log"
    if evidence is None:
        query_log.unlink()
    else:
        query_log.write_bytes(evidence)

    assert gate.run_gate("success", output_dir, console_log, None) == 1


def test_injection_recorded_only_in_csv_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    console = _START + _TARGETS + _TESTED_PARAMETER + _SCAN_DONE + _END
    csv = _CSV_HEADER + b"http://api.invalid/?q=1,GET,q,B,\n"
    assert _run_with_csv(tmp_path, console, csv) == 1
    assert "sanitized SQLMap evidence receipt" in capsys.readouterr().err


def test_completion_messages_out_of_order_do_not_prove_completion(
    tmp_path: Path,
) -> None:
    console = _END + _START + _TARGETS + _TESTED_PARAMETER + _SCAN_DONE
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


@pytest.mark.parametrize(
    "warning",
    [
        b"[WARNING] HTTP error codes detected during run:\n429 (Too Many Requests) - 1 times\n",
        b"[WARNING] skipping OpenAPI operation 'GET /bad' (no target)\n",
        b"[CRITICAL] connection timed out\n",
    ],
)
def test_scanner_reports_of_incomplete_coverage_fail(
    tmp_path: Path, warning: bytes
) -> None:
    console = _START + _TARGETS + _TESTED_PARAMETER + warning + _SCAN_DONE + _END
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_sqlmap_negative_result_message_is_not_a_failed_target(tmp_path: Path) -> None:
    negative = (
        b"[ERROR] all tested parameters do not appear to be injectable. "
        b"Try to increase values for '--level'/'--risk', skipping to the next target\n"
    )
    console = _START + _TARGETS + _TESTED_PARAMETER + negative + _SCAN_DONE + _END
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 0


@pytest.mark.parametrize(
    "csv",
    [b"", b"unexpected,header\n", _CSV_HEADER + b"bad,row\n", _CSV_HEADER + b'"bad'],
)
def test_malformed_or_empty_csv_fails_closed(tmp_path: Path, csv: bytes) -> None:
    assert _run_with_csv(tmp_path, _CLEAN_RUN, csv) == 1


def test_ansi_codes_inside_injection_marker_do_not_hide_finding(tmp_path: Path) -> None:
    console = (
        _CLEAN_RUN + b"sqlmap identified the following \x1b[1minjection point(s)\n"
    )
    assert _run_with_csv(tmp_path, console, _CSV_HEADER) == 1


def test_injection_marker_is_matched_inside_ansi_coloured_output(
    tmp_path: Path,
) -> None:
    code = _run(tmp_path, "success", _CLEAN_RUN + b"\x1b[1m" + _INJECTION)

    assert code == 1


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped", "", "unknown"])
def test_scan_step_that_did_not_succeed_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    outcome: str,
) -> None:
    code = _run(tmp_path, outcome, _CLEAN_RUN)

    assert code == 1
    assert "SQLMap scan step did not succeed" in capsys.readouterr().err


def test_run_killed_before_its_ending_marker_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _run(tmp_path, "success", _START + b"[INFO] tested the target\n")

    assert code == 1
    assert "does not prove the run completed" in capsys.readouterr().err


def test_run_with_only_an_ending_marker_fails_closed(tmp_path: Path) -> None:
    code = _run(tmp_path, "success", _END)

    assert code == 1


def test_missing_console_log_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(tmp_path, "success", None)

    assert code == 1
    assert "SQLMap produced no console log" in capsys.readouterr().err


def test_missing_result_log_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(tmp_path, "success", _CLEAN_RUN, result_log=None)

    assert code == 1
    assert "SQLMap produced no result log" in capsys.readouterr().err


def test_absent_output_directory_fails_closed(tmp_path: Path) -> None:
    code = gate.run_gate(
        "success",
        tmp_path / "absent-output",
        tmp_path / "absent-output" / "scan-console.log",
        None,
    )

    assert code == 1


def test_console_path_that_is_not_a_file_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir, _ = _layout(tmp_path, None)
    console_directory = output_dir / "scan-console.log"
    console_directory.mkdir()

    code = gate.run_gate("success", output_dir, console_directory, None)

    assert code == 1
    assert "SQLMap produced no console log" in capsys.readouterr().err


def test_evidence_file_that_cannot_be_read_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir, console_log = _layout(tmp_path, _CLEAN_RUN)
    real_read = Path.read_bytes

    def _deny(path: Path) -> bytes:
        if path == console_log:
            raise PermissionError("denied")
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", _deny)

    code = gate.run_gate("success", output_dir, console_log, None)

    assert code == 1
    assert "SQLMap evidence is unreadable: scan-console.log" in (
        capsys.readouterr().err
    )


def test_inaccessible_evidence_directory_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir, console_log = _layout(tmp_path, _CLEAN_RUN)
    hidden_dir = output_dir / "unreadable"
    hidden_dir.mkdir()
    (hidden_dir / "log").write_bytes(_INJECTION)
    scandir = os.scandir

    def deny_hidden(path):
        if Path(path) == hidden_dir:
            raise PermissionError("denied")
        return scandir(path)

    monkeypatch.setattr(os, "scandir", deny_hidden)
    assert gate.run_gate("success", output_dir, console_log, None) == 1


def test_summary_records_completion_and_result(tmp_path: Path) -> None:
    _run(tmp_path, "success", _CLEAN_RUN, summary=True)

    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Result: no confirmed injection. Run completed." in summary


def test_summary_records_confirmed_injection(tmp_path: Path) -> None:
    _run(tmp_path, "success", _CLEAN_RUN + _INJECTION, summary=True)

    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Result: confirmed injection. Run completed." in summary


def test_published_receipt_aggregates_failures_without_raw_content(
    tmp_path: Path,
) -> None:
    canary = b"private-canary.invalid/sensitive-payload"
    output_dir, _ = _layout(tmp_path, _CLEAN_RUN + canary, result_log=_INJECTION)
    (output_dir / "results.csv").write_bytes(
        _CSV_HEADER + b"https://" + canary + b",GET,q,B,\n"
    )
    receipt = tmp_path / "safe" / "receipt.json"

    status = gate.publish_evidence(output_dir, "success", "failure", "a" * 40, receipt)

    assert status == 0
    raw = receipt.read_bytes()
    assert canary not in raw
    assert b"sqlmap-output" not in raw
    document = json.loads(raw)
    assert document["source_sha"] == "a" * 40
    assert document["status"] == "failed"
    assert document["targets"] == 1
    assert document["tested_parameters"] == 3
    assert document["sqlmap_request_news_selects"] == 1
    assert document["csv_findings"] == 1
    assert document["confirmed_injection"] is True


def test_receipt_only_reports_allowlisted_parameter_and_technique_ids(
    tmp_path: Path,
) -> None:
    output_dir, _ = _layout(tmp_path, _CLEAN_RUN)
    (output_dir / "results.csv").write_bytes(
        _CSV_HEADER
        + b"http://127.0.0.1:8000/api/v1/news,GET,limit,BE,\n"
        + b"http://127.0.0.1:8000/api/v1/news,(custom) HEADER,if-none-match #1*,U,\n"
        + b"http://private.invalid,GET,untrusted-param,secret-technique,\n"
    )
    receipt = tmp_path / "receipt.json"

    assert (
        gate.publish_evidence(output_dir, "success", "failure", "a" * 40, receipt) == 0
    )
    raw = receipt.read_text(encoding="utf-8")
    document = json.loads(raw)
    assert document["finding_parameters"] == ["if-none-match", "limit", "unknown"]
    assert document["finding_techniques"] == ["boolean", "error", "union", "unknown"]
    assert "untrusted-param" not in raw
    assert "secret-technique" not in raw
    assert "127.0.0.1" not in raw


def test_published_receipt_preserves_unknown_missing_evidence(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"

    assert (
        gate.publish_evidence(
            tmp_path / "absent", "skipped", "failure", "b" * 40, receipt
        )
        == 0
    )

    document = json.loads(receipt.read_text(encoding="utf-8"))
    assert document["status"] == "failed"
    assert document["scan_outcome"] == "skipped"
    assert document["gate_outcome"] == "failure"
    assert document["targets"] is None
    assert document["tested_parameters"] is None
    assert document["sqlmap_request_news_selects"] is None
    assert document["csv_findings"] is None
    assert document["finding_parameters"] is None
    assert document["finding_techniques"] is None
    assert document["confirmed_injection"] is None


def test_receipt_rejects_invalid_source_sha_without_writing(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    assert (
        gate.publish_evidence(tmp_path, "success", "success", "not-a-sha", receipt) == 1
    )
    assert not receipt.exists()


def test_receipt_normalizes_untrusted_outcomes(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    assert (
        gate.publish_evidence(
            tmp_path / "missing", "sensitive-scan", "sensitive-gate", "c" * 40, receipt
        )
        == 0
    )
    raw = receipt.read_text(encoding="utf-8")
    assert "sensitive" not in raw
    document = json.loads(raw)
    assert document["scan_outcome"] == document["gate_outcome"] == "unknown"
    assert document["status"] == "failed"


def test_receipt_fails_if_success_is_not_backed_by_evidence(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    assert (
        gate.publish_evidence(
            tmp_path / "missing", "success", "success", "d" * 40, receipt
        )
        == 1
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "failed"


def test_receipt_marks_partial_and_malformed_counts_unknown(tmp_path: Path) -> None:
    output_dir, _ = _layout(tmp_path, _START + _TARGETS)
    (output_dir / "db-query-evidence.log").write_bytes(b"untrusted data\n")
    receipt = tmp_path / "receipt.json"

    assert (
        gate.publish_evidence(output_dir, "failure", "failure", "e" * 40, receipt) == 0
    )
    document = json.loads(receipt.read_text(encoding="utf-8"))
    assert document["targets"] == 1
    assert document["tested_parameters"] is None
    assert document["sqlmap_request_news_selects"] is None


def test_receipt_rejects_ambiguous_target_count(tmp_path: Path) -> None:
    output_dir, _ = _layout(tmp_path, _CLEAN_RUN + _TARGETS)
    receipt = tmp_path / "receipt.json"
    assert (
        gate.publish_evidence(output_dir, "failure", "failure", "e" * 40, receipt) == 0
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["targets"] is None


def test_receipt_write_failure_is_reported_without_raw_data(tmp_path: Path) -> None:
    assert (
        gate.publish_evidence(
            tmp_path / "missing", "failure", "failure", "e" * 40, tmp_path
        )
        == 1
    )


@pytest.mark.parametrize(
    "damage",
    ["missing_ending", "reordered_ending", "critical_error", "missing_result_log"],
)
def test_receipt_rejects_success_claim_without_complete_scan_evidence(
    tmp_path: Path, damage: str
) -> None:
    output_dir, console_log = _layout(tmp_path, _CLEAN_RUN)
    assert gate.run_gate("success", output_dir, console_log, None) == 0
    if damage == "missing_ending":
        console_log.write_bytes(_CLEAN_RUN.removesuffix(_END))
    elif damage == "reordered_ending":
        console_log.write_bytes(_END + _CLEAN_RUN.removesuffix(_END))
    elif damage == "critical_error":
        console_log.write_bytes(_CLEAN_RUN + b"[CRITICAL] connection failed\n")
    else:
        (output_dir / "api.invalid" / "log").unlink()

    assert gate.run_gate("success", output_dir, console_log, None) == 1
    receipt = tmp_path / "receipt.json"
    assert (
        gate.publish_evidence(output_dir, "success", "success", "a" * 40, receipt) == 1
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "failed"


def test_receipt_requires_tested_parameters_in_completion_validated_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir, console_log = _layout(tmp_path, _CLEAN_RUN)
    original_read_bytes = Path.read_bytes
    changed = False

    def read_while_log_changes(path: Path) -> bytes:
        nonlocal changed
        contents = original_read_bytes(path)
        if path == console_log and not changed:
            changed = True
            console_log.write_bytes(_START + _TARGETS + _SCAN_DONE + _END)
        return contents

    monkeypatch.setattr(Path, "read_bytes", read_while_log_changes)
    receipt = tmp_path / "receipt.json"
    assert (
        gate.publish_evidence(output_dir, "success", "success", "a" * 40, receipt) == 1
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "failed"


def test_receipt_rejects_injection_in_completion_validated_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir, console_log = _layout(tmp_path, _CLEAN_RUN)
    original_read_bytes = Path.read_bytes
    reads = 0

    def read_while_log_changes(path: Path) -> bytes:
        nonlocal reads
        contents = original_read_bytes(path)
        if path == console_log:
            reads += 1
            if reads == 2:
                console_log.write_bytes(_CLEAN_RUN + _INJECTION)
        return contents

    monkeypatch.setattr(Path, "read_bytes", read_while_log_changes)
    receipt = tmp_path / "receipt.json"
    assert (
        gate.publish_evidence(output_dir, "success", "success", "a" * 40, receipt) == 1
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "failed"


def test_receipt_command_publishes_verified_success(tmp_path: Path) -> None:
    output_dir, _ = _layout(tmp_path, _CLEAN_RUN)
    receipt = tmp_path / "receipt.json"
    assert (
        gate.main(
            [
                "publish-evidence",
                str(output_dir),
                "success",
                "success",
                "e" * 40,
                str(receipt),
            ]
        )
        == 0
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "passed"


@pytest.mark.parametrize("value", [-1, 1_000_001])
def test_receipt_does_not_publish_unbounded_counts(value: int) -> None:
    assert gate._bounded_count(value) is None


def test_main_parses_the_workflow_arguments(tmp_path: Path) -> None:
    output_dir, console_log = _layout(tmp_path, _CLEAN_RUN)

    code = gate.main(
        [
            "--scan-outcome",
            "success",
            "--output-dir",
            str(output_dir),
            "--console-log",
            str(console_log),
        ]
    )

    assert code == 0


def test_main_requires_every_evidence_argument() -> None:
    with pytest.raises(SystemExit):
        gate.main(["--scan-outcome", "success"])


def test_script_entry_point_exits_with_the_gate_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running the file as a script reaches the same exit status as main()."""

    output_dir, console_log = _layout(tmp_path, _CLEAN_RUN)
    script = Path(gate.__file__).resolve()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "--scan-outcome",
            "success",
            "--output-dir",
            str(output_dir),
            "--console-log",
            str(console_log),
        ],
    )
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(script), run_name="__main__")

    assert raised.value.code == 0
