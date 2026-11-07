"""Validate DAST targets and prepare privacy-safe scan evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from scripts.quality.nuclei_findings_gate import (
    ALLOWED_SEVERITIES,
    ExportError,
    _reject_duplicate_keys,
    _reject_nonfinite_constant,
    parse_records,
)


class PrivacyError(ValueError):
    """Raised when DAST evidence cannot be safely published."""


SARIF_SEVERITY = {
    "critical": ("error", "9.4"),
    "high": ("error", "8"),
    "medium": ("note", "5"),
    "low": ("note", "2"),
    "info": ("none", "1"),
    "unknown": ("none", "9.5"),
}
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024


def target_is_safe(target: str) -> bool:
    """Return whether the configured DAST target is safe to pass to scanners."""

    if (
        not target
        or any(char in target for char in "?#\\")
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in target)
    ):
        return False
    try:
        parsed = urlsplit(target)
        if parsed.port is not None and parsed.port == 0:
            return False
        if (
            not parsed.netloc.isascii()
            or (parsed.path and not re.fullmatch(r"/[A-Za-z0-9._~/-]*", parsed.path))
            or "//" in parsed.path
            or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        ):
            return False
        return bool(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and "%" not in parsed.netloc
        )
    except ValueError:
        return False


def _template_id(value: object, target: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]*", value
    ):
        raise PrivacyError("finding has an unsafe template identifier")
    parts = urlsplit(target)
    if parts.hostname and parts.hostname.casefold() in value.casefold():
        raise PrivacyError("finding identifier contains the target host")
    for segment in unquote(parts.path).split("/"):
        if len(segment) >= 3 and segment.casefold() in value.casefold():
            raise PrivacyError("finding identifier contains the target path")
    return value


def sanitize_findings(
    records: list[dict[str, Any]], target: str
) -> list[dict[str, Any]]:
    """Return a privacy-safe projection of native Nuclei findings."""

    if not target_is_safe(target):
        raise PrivacyError("invalid DAST target")
    findings = []
    for record in records:
        info = record.get("info")
        if (
            not isinstance(info, dict)
            or not isinstance(info.get("severity"), str)
            or info["severity"] not in ALLOWED_SEVERITIES
        ):
            raise PrivacyError("finding has an invalid severity")
        findings.append(
            {
                "template-id": _template_id(record.get("template-id"), target),
                "info": {"severity": info["severity"]},
            }
        )
    return findings


def _location_uri(uri: str, target: str) -> str:
    # Keep different endpoints distinguishable without publishing the URL or
    # query values. The digest identifies a target-neutral path; it is not an
    # encrypted copy of the scanner's raw request.
    for _ in range(3):
        uri = unquote(uri)
    uri = uri.partition("#")[0]
    uri, separator, query = uri.partition("?")
    if separator:
        names = [item.partition("=")[0] for item in query.split("&") if item]
        uri += "?" + "&".join(names)
    parsed = urlsplit(target)
    decoded_target = target
    decoded_path = parsed.path
    for _ in range(3):
        decoded_target = unquote(decoded_target)
        decoded_path = unquote(decoded_path)
    for private in (decoded_target, parsed.netloc, parsed.hostname or "", decoded_path):
        if private and private != "/":
            uri = re.sub(re.escape(private), "redacted", uri, flags=re.IGNORECASE)
    digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()
    return f"nuclei-redacted/{digest}.txt"


def sanitize_sarif(document: dict[str, Any], target: str) -> dict[str, Any]:
    """Return a privacy-safe Nuclei SARIF report."""

    if not target_is_safe(target):
        raise PrivacyError("invalid DAST target")
    try:
        if document["version"] != "2.1.0" or len(document["runs"]) != 1:
            raise PrivacyError("unexpected SARIF version or run count")
        run = document["runs"][0]
        driver = run["tool"]["driver"]
        version = driver["semanticVersion"]
        if (
            driver["name"] != "Nuclei"
            or not isinstance(version, str)
            or not re.fullmatch(r"v?\d+\.\d+\.\d+", version)
        ):
            raise PrivacyError("unexpected SARIF tool identity")
        rules: list[dict[str, Any]] = []
        indices: dict[str, int] = {}
        for rule in driver["rules"]:
            rule_id = _template_id(rule["id"], target)
            properties = rule["properties"]
            score = properties["security-severity"]
            if (
                rule_id in indices
                or properties["tags"] != ["security"]
                or not isinstance(score, str)
                or not re.fullmatch(r"(?:[0-9](?:\.\d+)?|10(?:\.0+)?)", score)
            ):
                raise PrivacyError("invalid SARIF rule")
            indices[rule_id] = len(rules)
            rules.append(
                {
                    "id": rule_id,
                    "name": rule_id,
                    "shortDescription": {"text": rule_id},
                    "fullDescription": {
                        "text": f"Nuclei template {rule_id} reported a finding."
                    },
                    "properties": {"tags": ["security"], "security-severity": score},
                }
            )
        results: list[dict[str, Any]] = []
        for result in run["results"]:
            rule_id = _template_id(result["ruleId"], target)
            level = result["level"]
            if rule_id not in indices or level not in {
                "none",
                "note",
                "warning",
                "error",
            }:
                raise PrivacyError("invalid SARIF finding")
            locations = result["locations"]
            if len(locations) != 1 or result["kind"] != "open":
                raise PrivacyError("invalid SARIF location or kind")
            uri = locations[0]["physicalLocation"]["artifactLocation"]["uri"]
            if not isinstance(uri, str) or not uri:
                raise PrivacyError("invalid SARIF location")
            results.append(
                {
                    "ruleId": rule_id,
                    "ruleIndex": indices[rule_id],
                    "level": level,
                    "kind": "open",
                    "message": {"text": f"Nuclei finding: {rule_id}"},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": _location_uri(uri, target)}
                            }
                        }
                    ],
                }
            )
        if not results:
            raise PrivacyError("empty SARIF cannot prove a clean scan")
        return {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Nuclei",
                            "organization": "ProjectDiscovery",
                            "product": "Nuclei",
                            "semanticVersion": version.removeprefix("v"),
                            "rules": rules,
                        }
                    },
                    "results": results,
                }
            ],
        }
    except (KeyError, TypeError, IndexError) as error:
        raise PrivacyError("malformed Nuclei SARIF report") from error


def sanitize_files(
    target: str, json_in: Path, sarif_in: Path, json_out: Path, sarif_out: Path
) -> int:
    """Write only filtered reports; never fabricate a clean SARIF result."""

    try:
        records = parse_records(json_in.read_text(encoding="utf-8"))
        findings = sanitize_findings(records, target)
        json_out.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
        if not sarif_in.is_file():
            if findings:
                raise PrivacyError("SARIF missing for findings")
            return 0
        if not findings:
            raise PrivacyError("unexpected SARIF for an empty JSON export")
        report = json.loads(
            sarif_in.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
        if not isinstance(report, dict):
            raise PrivacyError("SARIF root must be an object")
        clean_sarif = sanitize_sarif(report, target)
        run = clean_sarif["runs"][0]
        result_ids = Counter(result["ruleId"] for result in run["results"])
        if result_ids != Counter(record["template-id"] for record in findings):
            raise PrivacyError("JSON and SARIF findings do not agree")
        severities: dict[str, str] = {}
        for finding in findings:
            rule_id = finding["template-id"]
            severity = finding["info"]["severity"]
            if rule_id in severities and severities[rule_id] != severity:
                raise PrivacyError("one template has inconsistent severities")
            severities[rule_id] = severity
        for result in run["results"]:
            score = run["tool"]["driver"]["rules"][result["ruleIndex"]]["properties"][
                "security-severity"
            ]
            if (result["level"], score) != SARIF_SEVERITY[severities[result["ruleId"]]]:
                raise PrivacyError("JSON and SARIF severities do not agree")
        sarif_out.write_text(json.dumps(clean_sarif, indent=2) + "\n", encoding="utf-8")
        return 0
    except (OSError, UnicodeError, ExportError, PrivacyError, json.JSONDecodeError):
        print("::error::Could not safely publish Nuclei evidence.", file=sys.stderr)
        return 1


def _origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise PrivacyError("trace request is not an HTTP URL")
    return (
        parts.scheme,
        parts.hostname.casefold(),
        parts.port or (443 if parts.scheme == "https" else 80),
    )


def verify_scan(
    target: str,
    outcome: str,
    source_sha: str,
    trace_path: Path,
    log_path: Path,
    summary_path: Path,
) -> int:
    """Check bounded private evidence for a completed, effective scan.

    A response proves at least one request reached the origin; it does not
    establish that every selected template or request executed successfully.
    """

    try:
        if (
            not target_is_safe(target)
            or outcome != "success"
            or not re.fullmatch(r"[0-9a-f]{40}", source_sha)
        ):
            raise PrivacyError("scan identity or outcome is invalid")
        if any(
            path.stat().st_size > MAX_EVIDENCE_BYTES for path in (trace_path, log_path)
        ):
            raise PrivacyError("scan evidence exceeds the size limit")
        log = log_path.read_text(encoding="utf-8")
        if not re.search(r"(?m)^\[INF\] Scan completed in [^\r\n]+", log) or re.search(
            r"(?m)^\[INF\] Skipped .+ from target list as found unresponsive", log
        ):
            raise PrivacyError("scan completion evidence is absent or contains a skip")
        target_origin = _origin(target)
        responses = 0
        with trace_path.open(encoding="utf-8") as trace:
            for line in trace:
                record = json.loads(
                    line,
                    object_pairs_hook=_reject_duplicate_keys,
                    parse_constant=_reject_nonfinite_constant,
                )
                if not isinstance(record, dict) or not all(
                    isinstance(record.get(key), str)
                    for key in ("template", "type", "input", "address", "error")
                ):
                    raise PrivacyError("malformed trace record")
                if not record["input"] or not record["error"]:
                    raise PrivacyError("empty trace record field")
                if (
                    record["type"] == "http"
                    and _origin(record["input"]) == target_origin
                ):
                    if record["error"] != "none":
                        raise PrivacyError("same-origin HTTP request failed")
                    responses += 1
        if not responses:
            raise PrivacyError("no same-origin HTTP response observed")
        with summary_path.open("a", encoding="utf-8", newline="\n") as summary:
            summary.write(
                "### Nuclei scan execution\n\n"
                f"Source: `{source_sha}`. A same-origin HTTP response was observed "
                "and the scan reported completion. This does not establish "
                "coverage of every template request.\n"
            )
        return 0
    except (OSError, UnicodeError, ExportError, PrivacyError, ValueError):
        print(
            "::error::Could not verify Nuclei scan completion and execution.",
            file=sys.stderr,
        )
        return 1


def _register_target_masks(target: str) -> None:
    parts = urlsplit(target)
    path_segments = (segment for segment in parts.path.split("/") if len(segment) >= 3)
    for value in dict.fromkeys(
        (target, parts.netloc, parts.hostname, parts.path, *path_segments)
    ):
        if value and value != "/":
            print(f"::add-mask::{value.replace('%', '%25')}")


def prepare_target(output_path: Path) -> int:
    """Mask a dispatch or secret target before writing a private handoff."""

    created = False
    try:
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        secret = os.environ.get("DAST_SECRET_TARGET", "")
        if event_name == "schedule":
            target = secret
        elif event_name == "workflow_dispatch":
            event_path = Path(os.environ["GITHUB_EVENT_PATH"])
            event = json.loads(
                event_path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite_constant,
            )
            if not isinstance(event, dict):
                raise PrivacyError("event must be an object")
            inputs = event.get("inputs")
            if inputs is None:
                inputs = {}
            if not isinstance(inputs, dict):
                raise PrivacyError("dispatch inputs must be an object")
            supplied = inputs.get("target_url")
            if supplied is None:
                supplied = ""
            if not isinstance(supplied, str):
                raise PrivacyError("dispatch target must be text")
            target = supplied or secret
        else:
            raise PrivacyError("unexpected DAST event")
        if not target_is_safe(target):
            raise PrivacyError("invalid DAST target")
        _register_target_masks(target)
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(target)
        return 0
    except (KeyError, OSError, UnicodeError, ValueError, ExportError):
        if created:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
        print("::error::Could not prepare the DAST target safely.", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("validate-target")
    prepare = subparsers.add_parser("prepare-target")
    prepare.add_argument("--output", type=Path, required=True)
    sanitize = subparsers.add_parser("sanitize")
    for name in ("json-in", "sarif-in", "json-out", "sarif-out"):
        sanitize.add_argument(f"--{name}", type=Path, required=True)
    verify = subparsers.add_parser("verify-scan")
    for name in ("trace-in", "log-in", "summary-file"):
        verify.add_argument(f"--{name}", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.operation == "prepare-target":
        return prepare_target(arguments.output)
    if "DAST_TARGET_FILE" in os.environ:
        try:
            target = Path(os.environ["DAST_TARGET_FILE"]).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            print("::error::Could not read the private DAST target.", file=sys.stderr)
            return 1
    else:
        target = os.environ.get("TARGET_URL", "")
    if not target_is_safe(target):
        print(
            "::error::DAST target must be an HTTP(S) URL without credentials, "
            "query, fragment, whitespace, or an encoded/ambiguous path.",
            file=sys.stderr,
        )
        return 1
    if arguments.operation == "sanitize":
        return sanitize_files(
            target,
            arguments.json_in,
            arguments.sarif_in,
            arguments.json_out,
            arguments.sarif_out,
        )
    if arguments.operation == "verify-scan":
        return verify_scan(
            target,
            os.environ.get("SCAN_OUTCOME", ""),
            os.environ.get("GITHUB_SHA", ""),
            arguments.trace_in,
            arguments.log_in,
            arguments.summary_file,
        )
    _register_target_masks(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
