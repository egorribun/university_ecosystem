"""Privacy and exact-scope contracts for the SSR scanner diagnostic."""

import copy
import json
import os

import pytest

from scripts.quality import report_ssr_scanner_identities as report


def scan():
    return {
        "results": {
            path: [
                {
                    "filename": path,
                    "type": detector,
                    "line_number": line,
                    "hashed_secret": "a" * 40,
                    "secret_value": "MUST_NOT_BE_PRINTED",
                }
            ]
            for path, detector, line in report.EXPECTED
        }
    }


def test_exact_receipt_ignores_unreviewed_values():
    document = scan()
    document["results"]["unreviewed"] = [{"secret_value": "OTHER_PRIVATE_VALUE"}]
    before = copy.deepcopy(document)
    receipt = report.reviewed_identities(document, "b" * 40)
    assert document == before
    assert len(receipt["identities"]) == 3
    assert receipt["source_sha"] == "b" * 40
    assert "PRIVATE" not in json.dumps(receipt)
    assert "MUST_NOT" not in json.dumps(receipt)
    assert "unreviewed" not in json.dumps(receipt)
    for identity, (path, detector, line) in zip(
        receipt["identities"], report.EXPECTED, strict=True
    ):
        assert identity == {
            "path": path,
            "type": detector,
            "line": line,
            "hashed_secret": "a" * 40,
        }


@pytest.mark.parametrize(
    "field,value",
    [
        ("filename", "other"),
        ("type", "Private Key"),
        ("line_number", 95),
        ("line_number", True),
        ("hashed_secret", "private-canary"),
        ("hashed_secret", "A" * 40),
        ("hashed_secret", None),
    ],
)
def test_changed_identity_is_rejected(field, value):
    document = scan()
    document["results"][report.EXPECTED[0][0]][0][field] = value
    with pytest.raises(ValueError):
        report.reviewed_identities(document, "b" * 40)


@pytest.mark.parametrize("entries", [None, {}, [], "private-canary"])
def test_missing_or_invalid_reviewed_entries_are_rejected(entries):
    document = scan()
    document["results"][report.EXPECTED[0][0]] = entries
    with pytest.raises(ValueError):
        report.reviewed_identities(document, "b" * 40)


def test_duplicate_finding_is_rejected():
    document = scan()
    entries = document["results"][report.EXPECTED[0][0]]
    entries.append(copy.deepcopy(entries[0]))
    with pytest.raises(ValueError):
        report.reviewed_identities(document, "b" * 40)


@pytest.mark.parametrize("sha", ["", "0" * 40, "B" * 40, None])
def test_invalid_source_binding_is_rejected(sha):
    with pytest.raises(ValueError):
        report.reviewed_identities(scan(), sha)


@pytest.mark.parametrize("document", [None, [], {}, {"results": []}])
def test_invalid_document_is_rejected(document):
    with pytest.raises(ValueError):
        report.reviewed_identities(document, "b" * 40)


def test_main_success_outputs_only_receipt(tmp_path, capsys):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan()), encoding="utf-8")
    assert report.main([str(path), "--source-sha", "b" * 40]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out) == report.reviewed_identities(scan(), "b" * 40)


@pytest.mark.parametrize(
    "raw",
    [
        b"private-canary",
        b'{"results":{},"results":{}}',
        bytes([255]),
        json.dumps({"results": {}}).encode(),
    ],
)
def test_main_failure_never_prints_partial_identity_or_input(tmp_path, capsys, raw):
    path = tmp_path / "scan.json"
    path.write_bytes(raw)
    assert report.main([str(path), "--source-sha", "b" * 40]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "ERROR: reviewed SSR identity receipt unavailable.\n"


def test_oversized_and_missing_scan_are_safe(tmp_path, capsys, monkeypatch):
    path = tmp_path / "scan.json"
    assert report.main([str(path), "--source-sha", "b" * 40]) == 1
    path.write_bytes(b"private-canary")
    monkeypatch.setattr(report, "MAX_SCAN_BYTES", 3)
    assert report.main([str(path), "--source-sha", "b" * 40]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.count("receipt unavailable") == 2


def test_late_invalid_identity_emits_no_partial_receipt(tmp_path, capsys):
    document = scan()
    document["results"][report.EXPECTED[-1][0]][0]["hashed_secret"] = "private-canary"
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert report.main([str(path), "--source-sha", "b" * 40]) == 1
    assert capsys.readouterr().out == ""


def test_reviewed_repository_sources_match_exact_blobs():
    report.validate_sources(report.Path(__file__).resolve().parents[1])


def test_changed_or_redirected_source_is_rejected(tmp_path, monkeypatch):
    relative = "source.go"
    path = tmp_path / relative
    path.write_bytes(b"reviewed")
    blob = b"blob 8" + bytes([0]) + b"reviewed"
    digest = report.hashlib.sha1(blob, usedforsecurity=False).digest()
    monkeypatch.setattr(report, "EXPECTED_BLOBS", {relative: digest})
    report.validate_sources(tmp_path)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError):
        report.validate_sources(tmp_path)
    path.unlink()
    target = tmp_path / "target.go"
    target.write_bytes(b"reviewed")
    path.symlink_to(target)
    with pytest.raises(OSError):
        report.validate_sources(tmp_path)


def test_fifo_and_directory_are_rejected_without_blocking(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        report.read_regular(fifo, 100)
    with pytest.raises((OSError, ValueError)):
        report.read_regular(tmp_path, 100)


def test_source_validation_failure_has_generic_error(tmp_path, capsys, monkeypatch):
    def fail(_root):
        raise ValueError("private-source-content")

    monkeypatch.setattr(report, "validate_sources", fail)
    assert report.main([str(tmp_path / "unused"), "--source-sha", "b" * 40]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "ERROR: reviewed SSR identity receipt unavailable.\n"


def test_git_blob_digest_matches_independent_empty_blob_identity():
    # Canonical Git empty-blob object ID, not computed through the helper.
    expected = bytes((
        230, 157, 226, 155, 178, 209, 214, 67, 75, 139,
        41, 174, 119, 90, 216, 194, 228, 140, 83, 145,
    ))
    assert report.git_blob_digest(b"") == expected
