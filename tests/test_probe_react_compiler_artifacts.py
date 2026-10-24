"""Stdlib-only contracts for the non-executing React compiler artifact probe."""

from __future__ import annotations

import base64
import gzip
import hashlib
import importlib.util
import io
import json
import tarfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "ci"
    / "probe_react_compiler_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "react_compiler_artifact_probe", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

BABEL = "babel-plugin-react-compiler"
ESLINT = "eslint-plugin-react-compiler"
CUTOFF = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
SOURCE = b'const evidence = "SOURCE_MUST_NOT_APPEAR_IN_REPORT"; require("zod");'
LICENSE = b"MIT license fixture\n"


def sri(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


def archive(
    *,
    name: str = BABEL,
    version: str = "1.0.0",
    source: bytes = SOURCE,
    extra: tuple[str, bytes, bytes] | None = None,
    duplicate: bool = False,
    scripts: dict[str, str] | None = None,
) -> bytes:
    """Produce actual tar/gzip bytes; no package code is executed."""
    entries = [
        (
            "package/package.json",
            json.dumps(
                {
                    "name": name,
                    "version": version,
                    "dependencies": {"zod": "^4.6.6"},
                    "scripts": scripts or {"postinstall": "MUST_NOT_EXECUTE"},
                }
            ).encode(),
            tarfile.REGTYPE,
        ),
        ("package/dist/index.js", source, tarfile.REGTYPE),
        ("package/LICENSE", LICENSE, tarfile.REGTYPE),
    ]
    if extra is not None:
        entries.append(extra)
    if duplicate:
        entries.append(entries[1])
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as handle:
        for path, data, kind in entries:
            entry = tarfile.TarInfo(path)
            entry.type = kind
            entry.size = len(data) if kind == tarfile.REGTYPE else 0
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                entry.linkname = "../../outside"
            handle.addfile(entry, io.BytesIO(data) if entry.size else None)
    return gzip.compress(output.getvalue(), mtime=0)


def metadata(name: str, version: str, integrity: str) -> dict[str, Any]:
    return {
        "name": name,
        "version": version,
        "dist": {
            "integrity": integrity,
            "tarball": f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz",
        },
    }


def packuments() -> dict:
    versions = {
        BABEL: [
            ("1.0.0", "2025-10-07T00:00:00Z"),
            ("1.0.1", "2026-10-16T00:00:00Z"),
            ("1.0.2", "2026-10-18T00:00:00Z"),
            ("0.0.0-experimental-old", "2026-10-16T01:00:00Z"),
            ("0.0.0-experimental-new", "2026-10-18T01:00:00Z"),
        ],
        ESLINT: [
            ("19.1.0-rc.2", "2025-04-21T00:00:00Z"),
            ("19.1.0-rc.3", "2026-10-17T00:00:00Z"),
        ],
    }
    return {
        name: {
            "name": name,
            "dist-tags": {"latest": items[-1][0]},
            "time": dict(items),
            "versions": {
                version: {"name": name, "version": version} for version, _ in items
            },
        }
        for name, items in versions.items()
    }


class CandidateContracts(unittest.TestCase):
    def test_selects_exact_controls_and_at_most_three_mature_alternatives(self) -> None:
        self.assertEqual(
            probe.select_candidates(packuments(), CUTOFF),
            [
                (BABEL, "1.0.0"),
                (ESLINT, "19.1.0-rc.2"),
                (BABEL, "1.0.1"),
                (BABEL, "0.0.0-experimental-old"),
                (ESLINT, "19.1.0-rc.3"),
            ],
        )

    def test_excludes_tagged_latest_one_second_younger_than_cutoff(self) -> None:
        data = packuments()
        data[ESLINT]["time"]["19.1.0-rc.3"] = "2026-10-17T00:00:01Z"
        result = probe.select_candidates(data, CUTOFF)
        self.assertIsInstance(result, list)
        self.assertNotIn((ESLINT, "19.1.0-rc.3"), result)
        self.assertEqual(len(result), 4)

    def test_deduplicates_controls_without_arbitrary_fillers(self) -> None:
        data = packuments()
        for name, version in ((BABEL, "1.0.0"), (ESLINT, "19.1.0-rc.2")):
            data[name]["time"] = {version: "2025-10-01T00:00:00Z"}
            data[name]["versions"] = {version: {"name": name, "version": version}}
        self.assertEqual(
            probe.select_candidates(data, CUTOFF),
            [(BABEL, "1.0.0"), (ESLINT, "19.1.0-rc.2")],
        )

    def test_control_without_authoritative_publication_time_fails_closed(self) -> None:
        data = packuments()
        del data[BABEL]["time"]["1.0.0"]
        with self.assertRaises(probe.ProbeError):
            probe.select_candidates(data, CUTOFF)

    def test_control_newer_than_cutoff_fails_closed(self) -> None:
        data = packuments()
        data[BABEL]["time"]["1.0.0"] = "2026-10-18T00:00:00Z"
        with self.assertRaises(probe.ProbeError):
            probe.select_candidates(data, CUTOFF)

    def test_naive_cutoff_cannot_bypass_timezone_comparison(self) -> None:
        with self.assertRaises(probe.ProbeError):
            probe.select_candidates(packuments(), datetime(2026, 10, 17))

    def test_metadata_url_must_match_exact_allowed_package_and_version(self) -> None:
        valid = metadata(BABEL, "1.0.0", sri(b"fixture"))
        request = probe.artifact_request(BABEL, "1.0.0", valid)
        self.assertIsInstance(request, dict)
        self.assertEqual(
            request["url"],
            "https://registry.npmjs.org/babel-plugin-react-compiler/-/"
            "babel-plugin-react-compiler-1.0.0.tgz",
        )

    def test_request_rejects_wrong_origins_credentials_queries_versions(self) -> None:
        for value in (
            "https://example.invalid/archive.tgz",
            "https://user@registry.npmjs.org/archive.tgz",
            "http://registry.npmjs.org/archive.tgz",
            "https://registry.npmjs.org/babel-plugin-react-compiler/-/"
            "babel-plugin-react-compiler-1.0.0.tgz?token=private",
            "https://registry.npmjs.org/babel-plugin-react-compiler/-/"
            "babel-plugin-react-compiler-1.0.1.tgz",
        ):
            with self.subTest(value=value):
                data = metadata(BABEL, "1.0.0", sri(b"fixture"))
                data["dist"]["tarball"] = value
                with self.assertRaises(probe.ProbeError):
                    probe.artifact_request(BABEL, "1.0.0", data)

    def test_registry_control_must_match_deployed_integrity(self) -> None:
        data = metadata(BABEL, "1.0.0", sri(b"new"))
        with self.assertRaises(probe.ProbeError):
            probe.artifact_request(
                BABEL, "1.0.0", data, locked_integrity=sri(b"deployed")
            )

    def test_bad_integrity_and_unknown_package_are_rejected(self) -> None:
        for integrity in ("sha1-aGVsbG8=", "sha512-!!!", "sha512-aGVsbG8="):
            with self.subTest(integrity=integrity):
                with self.assertRaises(probe.ProbeError):
                    probe.artifact_request(
                        BABEL, "1.0.0", metadata(BABEL, "1.0.0", integrity)
                    )
        with self.assertRaises(probe.ProbeError):
            probe.artifact_request(
                "unapproved-package",
                "1.0.0",
                metadata("unapproved-package", "1.0.0", sri(b"fixture")),
            )


class ProvenanceContracts(unittest.TestCase):
    def test_matching_registry_and_manifest_revisions_are_corroborated(self) -> None:
        revision = "a" * 40
        result = probe.artifact_provenance({"gitHead": revision}, {"gitHead": revision})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["source_revision"], revision)
        self.assertEqual(result["provenance_status"], "corroborated")
        self.assertEqual(result["source_binding"], "unverified")

    def test_registry_only_revision_does_not_claim_artifact_source_proof(self) -> None:
        revision = "a" * 40
        result = probe.artifact_provenance({"gitHead": revision}, {})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["source_revision"], revision)
        self.assertEqual(result["provenance_status"], "registry_only")
        self.assertEqual(result["source_binding"], "unverified")

    def test_manifest_only_revision_does_not_claim_registry_corroboration(self) -> None:
        revision = "b" * 40
        result = probe.artifact_provenance({}, {"gitHead": revision})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["source_revision"], revision)
        self.assertEqual(result["provenance_status"], "manifest_only")
        self.assertEqual(result["source_binding"], "unverified")

    def test_missing_revisions_are_reported_as_absent_not_inferred(self) -> None:
        result = probe.artifact_provenance({}, {})
        self.assertIsInstance(result, dict)
        self.assertIsNone(result["source_revision"])
        self.assertEqual(result["provenance_status"], "absent")
        self.assertEqual(result["source_binding"], "unverified")

    def test_conflicting_registry_and_manifest_revisions_fail_closed(self) -> None:
        with self.assertRaises(probe.ProbeError):
            probe.artifact_provenance({"gitHead": "a" * 40}, {"gitHead": "b" * 40})

    def test_malformed_revisions_fail_closed_in_either_location(self) -> None:
        for invalid in (None, 12, "a" * 39, "a" * 41, "g" * 40, "A" * 40):
            with self.subTest(value=invalid):
                with self.assertRaises(probe.ProbeError):
                    probe.artifact_provenance({"gitHead": invalid}, {})
                with self.assertRaises(probe.ProbeError):
                    probe.artifact_provenance({}, {"gitHead": invalid})

    def test_main_preserves_registry_revision_in_each_validated_artifact(self) -> None:
        revisions = {BABEL: "b" * 40, ESLINT: "c" * 40}
        responses: dict[str, bytes] = {}
        locked: dict[str, Any] = {}
        for name, version in ((BABEL, "1.0.0"), (ESLINT, "19.1.0-rc.2")):
            artifact = archive(name=name, version=version)
            entry = metadata(name, version, sri(artifact))
            entry["gitHead"] = revisions[name]
            responses[entry["dist"]["tarball"]] = artifact
            responses[f"https://registry.npmjs.org/{name}"] = json.dumps(
                {
                    "name": name,
                    "versions": {version: entry},
                    "time": {version: "2025-01-01T00:00:00Z"},
                }
            ).encode()
            locked[f"node_modules/{name}"] = {
                "version": version,
                "integrity": sri(artifact),
            }

        def fixture_fetch(url: str, limit: int) -> bytes:
            self.assertIn(url, responses)
            data = responses[url]
            self.assertLessEqual(len(data), limit)
            return data

        output = io.StringIO()
        with TemporaryDirectory(prefix="react-probe-contract-") as directory:
            root = Path(directory)
            lock_path = root / "frontend" / "package-lock.json"
            lock_path.parent.mkdir(parents=True)
            lock_path.write_text(json.dumps({"packages": locked}), encoding="utf-8")
            module_path = root / "scripts" / "ci" / "probe_react_compiler_artifacts.py"
            with (
                patch.object(probe, "__file__", str(module_path)),
                patch.dict(probe.os.environ, {"SOURCE_SHA": "a" * 40}),
                patch.object(probe, "fetch_bounded", side_effect=fixture_fetch),
                redirect_stdout(output),
            ):
                probe.main()

        report = json.loads(output.getvalue())
        self.assertEqual(len(report["candidates"]), 2)
        for candidate in report["candidates"]:
            self.assertIn("source_provenance", candidate)
            self.assertEqual(
                candidate["source_provenance"]["source_revision"],
                revisions[candidate["name"]],
            )
            self.assertEqual(
                candidate["source_provenance"]["provenance_status"], "registry_only"
            )
            self.assertEqual(
                candidate["source_provenance"]["source_binding"], "unverified"
            )


class ArchiveContracts(unittest.TestCase):
    def inspect(self, data: bytes, **kwargs: Any) -> dict[str, Any] | None:
        return probe.inspect_artifact(
            data,
            BABEL,
            "1.0.0",
            kwargs.pop("integrity", sri(data)),
            **kwargs,
        )

    def test_reports_hashes_and_hints_without_source_or_execution_claim(self) -> None:
        data = archive()
        result = self.inspect(data)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], BABEL)
        self.assertEqual(result["version"], "1.0.0")
        self.assertEqual(result["tarball_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(
            result["files"]["package/dist/index.js"]["sha256"],
            hashlib.sha256(SOURCE).hexdigest(),
        )
        self.assertEqual(result["files"]["package/LICENSE"]["size"], len(LICENSE))
        self.assertTrue(result["has_lifecycle_scripts"])
        self.assertEqual(result["signals"]["external_zod_root"], 1)
        self.assertEqual(result["patched_status"], "not_established")
        self.assertNotIn("SOURCE_MUST_NOT_APPEAR_IN_REPORT", json.dumps(result))
        self.assertNotIn("MUST_NOT_EXECUTE", json.dumps(result))

    def test_report_includes_source_provenance(self) -> None:
        result = self.inspect(archive())
        self.assertIsInstance(result, dict)
        self.assertIn("source_provenance", result)
        self.assertEqual(result["source_provenance"]["provenance_status"], "absent")
        self.assertEqual(result["source_provenance"]["source_binding"], "unverified")

    def test_prepare_only_lifecycle_script_is_reported_without_execution(self) -> None:
        result = self.inspect(archive(scripts={"prepare": "MUST_NOT_EXECUTE"}))
        self.assertIsInstance(result, dict)
        self.assertTrue(result["has_lifecycle_scripts"])
        self.assertNotIn("MUST_NOT_EXECUTE", json.dumps(result))

    def test_patch_tokens_are_only_hints_and_never_a_clean_verdict(self) -> None:
        data = archive(
            source=b"// $ZodArray capSize(inst, arraySize); sizeCaps generateSizeGate"
        )
        result = self.inspect(data)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["patched_status"], "not_established")
        self.assertGreater(result["signals"]["capSize"], 0)

    def test_tampered_bytes_rejected_before_tar_parsing(self) -> None:
        data = archive()
        with self.assertRaises(probe.ProbeError):
            self.inspect(data + b"tamper", integrity=sri(data))

    def test_manifest_name_or_version_mismatch_is_not_an_artifact_match(self) -> None:
        for data in (archive(name=ESLINT), archive(version="1.0.1")):
            with self.subTest(data_hash=hashlib.sha256(data).hexdigest()):
                with self.assertRaises(probe.ProbeError):
                    self.inspect(data)

    def test_rejects_traversal_absolute_windows_and_wrong_prefix_paths(self) -> None:
        for path in (
            "package/../outside",
            "/outside",
            "package\\outside",
            "other/index.js",
            "package//outside",
            "package/./outside",
        ):
            with self.subTest(path=path):
                with self.assertRaises(probe.ProbeError):
                    self.inspect(archive(extra=(path, b"unsafe", tarfile.REGTYPE)))

    def test_links_devices_and_fifos_are_rejected_without_extracting(self) -> None:
        for kind in (
            tarfile.SYMTYPE,
            tarfile.LNKTYPE,
            tarfile.CHRTYPE,
            tarfile.FIFOTYPE,
        ):
            with self.subTest(kind=kind):
                with self.assertRaises(probe.ProbeError):
                    self.inspect(archive(extra=("package/unsafe", b"", kind)))

    def test_duplicate_member_paths_fail_closed(self) -> None:
        with self.assertRaises(probe.ProbeError):
            self.inspect(archive(duplicate=True))

    def test_inflated_payload_limit_is_enforced(self) -> None:
        with self.assertRaises(probe.ProbeError):
            self.inspect(archive(source=b"x" * 100_000), max_unpacked=20_000)

    def test_file_count_limit_is_enforced(self) -> None:
        with self.assertRaises(probe.ProbeError):
            self.inspect(archive(), max_members=2)

    def test_malformed_gzip_fails_with_sanitized_probe_error(self) -> None:
        with self.assertRaises(probe.ProbeError):
            self.inspect(b"not a gzip archive")

    def test_invalid_utf8_source_is_rejected(self) -> None:
        with self.assertRaises(probe.ProbeError):
            self.inspect(archive(source=b"\xff"))

    def test_missing_script_entry_is_not_an_inspected_compiler(self) -> None:
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as handle:
            raw = json.dumps({"name": BABEL, "version": "1.0.0"}).encode()
            member = tarfile.TarInfo("package/package.json")
            member.size = len(raw)
            handle.addfile(member, io.BytesIO(raw))
        with self.assertRaises(probe.ProbeError):
            self.inspect(gzip.compress(output.getvalue(), mtime=0))


class RegistryResponse(io.BytesIO):
    def __init__(
        self,
        body: bytes = b"abc",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class ResponseContracts(unittest.TestCase):
    def test_reads_bounded_response_bytes(self) -> None:
        self.assertEqual(probe.read_bounded(io.BytesIO(b"abc"), 3), b"abc")

    def test_response_over_limit_is_rejected(self) -> None:
        with self.assertRaises(probe.ProbeError):
            probe.read_bounded(io.BytesIO(b"abcd"), 3)

    def test_unapproved_request_target_is_rejected_without_transport(self) -> None:
        def must_not_open(*_args: Any, **_kwargs: Any) -> None:
            self.fail("unapproved network target reached transport")

        with self.assertRaises(probe.ProbeError):
            probe.fetch_bounded(
                "https://example.invalid/private", 100, opener=must_not_open
            )

    def test_fixed_https_transport_has_timeout_and_no_redirect_following(self) -> None:
        url = f"https://registry.npmjs.org/{BABEL}"
        with patch.object(probe.http.client, "HTTPSConnection") as transport:
            connection = transport.return_value
            connection.getresponse.return_value = RegistryResponse()
            self.assertEqual(probe.fetch_bounded(url, 3), b"abc")
            transport.assert_called_once_with("registry.npmjs.org", timeout=20)
            self.assertEqual(connection.request.call_args.args, ("GET", f"/{BABEL}"))
            connection.getresponse.assert_called_once_with()
            connection.close.assert_called_once_with()

    def test_redirect_and_error_statuses_are_rejected_without_following(self) -> None:
        for status in (301, 302, 307, 308, 400, 429, 500):
            with self.subTest(status=status):
                with patch.object(probe.http.client, "HTTPSConnection") as transport:
                    connection = transport.return_value
                    response = RegistryResponse(status=status)
                    response.headers["Location"] = "https://example.invalid/private"
                    connection.getresponse.return_value = response
                    with self.assertRaises(probe.ProbeError):
                        probe.fetch_bounded(f"https://registry.npmjs.org/{BABEL}", 3)
                    self.assertEqual(connection.request.call_count, 1)
                    connection.close.assert_called_once_with()

    def test_advertised_length_is_bounded_before_body_read(self) -> None:
        for length in ("4", "-1", "not-a-size", "9" * 40):
            with self.subTest(length=length):
                response = RegistryResponse(headers={"Content-Length": length})
                with patch.object(probe, "_registry_response") as transport:
                    transport.return_value = response
                    with self.assertRaises(probe.ProbeError):
                        probe.fetch_bounded(f"https://registry.npmjs.org/{BABEL}", 3)

    def test_unadvertised_response_overflow_is_rejected(self) -> None:
        with patch.object(probe, "_registry_response") as transport:
            transport.return_value = RegistryResponse(b"abcd")
            with self.assertRaises(probe.ProbeError):
                probe.fetch_bounded(f"https://registry.npmjs.org/{BABEL}", 3)

    def test_transport_timeout_becomes_sanitized_probe_error(self) -> None:
        with patch.object(probe, "_registry_response") as transport:
            transport.side_effect = TimeoutError("PRIVATE_TRANSPORT_DETAIL")
            with self.assertRaises(probe.ProbeError) as error:
                probe.fetch_bounded(f"https://registry.npmjs.org/{BABEL}", 3)
            self.assertNotIn("PRIVATE_TRANSPORT_DETAIL", str(error.exception))

    def test_unexpected_content_encoding_is_rejected(self) -> None:
        with patch.object(probe, "_registry_response") as transport:
            transport.return_value = RegistryResponse(
                headers={"Content-Encoding": "gzip"}
            )
            with self.assertRaises(probe.ProbeError):
                probe.fetch_bounded(f"https://registry.npmjs.org/{BABEL}", 3)

    def test_read_deadline_is_enforced(self) -> None:
        with patch.object(probe.time, "monotonic", side_effect=(0, 61)):
            with self.assertRaises(probe.ProbeError):
                probe.read_bounded(io.BytesIO(b"abc"), 3)

    def test_bounded_reader_uses_incremental_reads_not_read_to_fill(self) -> None:
        class IncrementalResponse:
            def __init__(self) -> None:
                self.chunks = iter((b"abc", b""))

            def read(self, _limit: int) -> bytes:
                raise AssertionError("read-to-fill must not be called")

            def read1(self, _limit: int) -> bytes:
                return next(self.chunks)

        self.assertEqual(probe.read_bounded(IncrementalResponse(), 3), b"abc")

    def test_cli_total_deadline_installs_and_restores_alarm(self) -> None:
        with (
            patch.object(probe.signal, "signal", return_value="previous") as handler,
            patch.object(probe.signal, "alarm") as alarm,
            patch.object(probe, "main") as main,
        ):
            probe._run_with_deadline()
            main.assert_called_once_with()
            self.assertEqual(
                [call.args for call in alarm.call_args_list], [(420,), (0,)]
            )
            self.assertEqual(handler.call_args.args, (probe.signal.SIGALRM, "previous"))
            expired = handler.call_args_list[0].args[1]
            with self.assertRaises(probe.ProbeError):
                expired(probe.signal.SIGALRM, None)

    def test_cli_total_deadline_is_restored_after_failure(self) -> None:
        with (
            patch.object(probe.signal, "signal", return_value="previous") as handler,
            patch.object(probe.signal, "alarm") as alarm,
            patch.object(probe, "main", side_effect=probe.ProbeError("fixture")),
        ):
            with self.assertRaises(probe.ProbeError):
                probe._run_with_deadline()
            alarm.assert_called_with(0)
            handler.assert_called_with(probe.signal.SIGALRM, "previous")


if __name__ == "__main__":
    unittest.main()
