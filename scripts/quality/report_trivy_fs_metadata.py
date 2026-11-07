import copy
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import threading
from pathlib import Path

MAX_BYTES = 4 * 1024 * 1024
MAX_TRACKED_DIFF_BYTES = 262144
MAX_TRACKED_DIFF_PATHS = 4096
PREFIX = "TRIVY_FS_METADATA "
ID = re.compile(
    r"(?:CVE-[0-9]{4}-[0-9]{4,12}|GHSA-[a-z0-9]{4}(?:-[a-z0-9]{4}){2}|RUSTSEC-[0-9]{4}-[0-9]{4,8}|GO-[0-9]{4}-[0-9]{4,8})"
)
PACKAGE = re.compile(r"[A-Za-z0-9@][A-Za-z0-9@._/+~:-]{0,255}")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+~:,<>=^|*() -]{0,511}")


def require(condition):
    if not condition:
        raise ValueError("invalid diagnostic input")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def finite_float(value):
    result = float(value)
    require(math.isfinite(result))
    return result


def reject_constant(_value):
    raise ValueError("invalid JSON constant")


def project(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES)
    text = raw.decode("utf-8")
    depth, quoted, escaped = 0, False, False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            require(depth <= 24)
        elif character in "]}":
            depth -= 1
            require(depth >= 0)
    require(depth == 0 and not quoted and not escaped)
    document = json.loads(
        text,
        object_pairs_hook=unique_object,
        parse_float=finite_float,
        parse_constant=reject_constant,
    )
    require(type(document) is dict and document.get("version") == "2.1.0")
    runs = document.get("runs")
    require(type(runs) is list and len(runs) == 1 and type(runs[0]) is dict)
    run = runs[0]
    driver = run["tool"]["driver"]
    require(type(driver) is dict and driver.get("name") == "Trivy")
    require(driver.get("version") == "0.75.0")
    rules, results = driver.get("rules", []), run.get("results", [])
    require(type(rules) is list and len(rules) <= 128)
    require(type(results) is list and len(results) <= 128)
    for rule in rules:
        require(type(rule) is dict and type(rule.get("id")) is str)
        require(ID.fullmatch(rule["id"]) is not None)
        require(
            rule.get("name")
            in ("OsPackageVulnerability", "LanguageSpecificPackageVulnerability")
        )
    require(len({rule["id"] for rule in rules}) == len(rules))
    records = []
    for result in results:
        require(type(result) is dict and type(result.get("ruleId")) is str)
        identifier, index = result["ruleId"], result.get("ruleIndex")
        require(ID.fullmatch(identifier) is not None)
        require(type(index) is int and 0 <= index < len(rules))
        require(rules[index]["id"] == identifier)
        message = result["message"]["text"]
        require(type(message) is str and len(message) <= 2048 and "\r" not in message)
        lines = message.split("\n")
        prefixes = (
            "Package: ",
            "Installed Version: ",
            "Vulnerability ",
            "Severity: ",
            "Fixed Version: ",
        )
        require(
            len(lines) == 6
            and all(
                line.startswith(prefix)
                for line, prefix in zip(lines[:5], prefixes, strict=True)
            )
        )
        package, installed, described_id, severity, fixed = [
            line[len(prefix) :]
            for line, prefix in zip(lines[:5], prefixes, strict=True)
        ]
        require(described_id == identifier and severity in ("HIGH", "CRITICAL"))
        require(PACKAGE.fullmatch(package) is not None)
        require(VERSION.fullmatch(installed) is not None)
        require(fixed == "" or VERSION.fullmatch(fixed) is not None)
        require(
            lines[5].startswith("Link: [" + identifier + "](")
            and lines[5].endswith(")")
        )
        records.append(
            {
                "id": identifier,
                "package": package,
                "installed": installed,
                "fixed": fixed,
                "severity": severity,
            }
        )
    return sorted(
        records,
        key=lambda record: tuple(
            record[key] for key in ("id", "package", "installed", "fixed", "severity")
        ),
    )


def git(operation, limit=1024, raw=False):
    options = {
        "check": False,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "timeout": 10,
    }
    if operation == "head":
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "rev-parse",
                "--verify",
                "HEAD",
            ],
            **options,
        )
    elif operation == "commit-size":
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "cat-file",
                "-s",
                "HEAD",
            ],
            **options,
        )
    elif operation == "commit":
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "cat-file",
                "commit",
                "HEAD",
            ],
            **options,
        )
    elif operation == "tracked-clean":
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "diff",
                "--quiet",
                "--no-ext-diff",
                "--no-textconv",
                "HEAD",
                "--",
            ],
            **options,
        )
    elif operation == "workflow-blob":
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "rev-parse",
                "HEAD:.github/workflows/reusable-security-audit.yml",
            ],
            **options,
        )
    else:
        raise ValueError("unsupported fixed Git diagnostic operation")
    require(result.returncode == 0 and len(result.stdout) <= limit)
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def classify_tracked_changes(raw):
    require(
        type(raw) is bytes
        and 0 < len(raw) <= MAX_TRACKED_DIFF_BYTES
        and raw.endswith(b"\0")
    )
    fields = raw[:-1].split(b"\0")
    require(len(fields) % 2 == 0 and 0 < len(fields) // 2 <= MAX_TRACKED_DIFF_PATHS)
    seen = set()
    known = False
    for status, path in zip(fields[::2], fields[1::2], strict=True):
        require(status in (b"A", b"D", b"M", b"T", b"U", b"X", b"B"))
        require(path and path not in seen)
        seen.add(path)
        if (
            status == b"M"
            and path == b"charts/university-ecosystem/charts/redis-0.1.0.tgz"
        ):
            known = True
    count = len(seen)
    return {
        "knownRedisTgzModified": known,
        "unknownPathCount": count - int(known),
        "changedCount": count,
    }


def bounded_process_output(process, timeout=10):
    require(process.stdout is not None)
    data, errors = bytearray(), []

    def collect():
        try:
            while len(data) <= MAX_TRACKED_DIFF_BYTES:
                chunk = os.read(
                    process.stdout.fileno(),
                    min(8192, MAX_TRACKED_DIFF_BYTES + 1 - len(data)),
                )
                if not chunk:
                    return
                data.extend(chunk)
                if len(data) > MAX_TRACKED_DIFF_BYTES:
                    try:
                        process.kill()
                    except OSError:
                        pass
                    return
        except OSError:
            errors.append(True)

    reader = threading.Thread(target=collect, daemon=True)
    try:
        reader.start()
    except Exception:
        process.kill()
        process.wait(timeout=1)
        process.stdout.close()
        raise
    try:
        try:
            status = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
            reader.join(timeout=1)
            raise
        reader.join(timeout=1)
        require(
            not reader.is_alive()
            and status == 0
            and not errors
            and len(data) <= MAX_TRACKED_DIFF_BYTES
        )
        return bytes(data)
    finally:
        if not reader.is_alive():
            process.stdout.close()


def tracked_diff_process():
    return subprocess.Popen(
        [
            "/usr/bin/git",
            "--no-optional-locks",
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "diff",
            "--name-status",
            "-z",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "HEAD",
            "--",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=False,
    )


def bounded_tracked_diff():
    return classify_tracked_changes(bounded_process_output(tracked_diff_process()))


def identity():
    global identity_check
    identity_check = "source-format"
    tested, source = os.environ["GITHUB_SHA"], os.environ["EXPECTED_SOURCE_SHA"]
    require(all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (tested, source)))
    identity_check = "checkout-head"
    require(git("head") == tested)
    identity_check = "source-parent"
    if source != tested:
        size = git("commit-size")
        require(
            re.fullmatch(r"[1-9][0-9]{0,5}", size) is not None and int(size) <= 65536
        )
        commit = git("commit", limit=65536, raw=True)
        require(len(commit) == int(size) and b"\n\n" in commit)
        headers = commit.split(b"\n\n", 1)[0].split(b"\n")
        parents = [
            line[7:].decode("ascii") for line in headers if line.startswith(b"parent ")
        ]
        require(
            len(parents) == 2
            and all(re.fullmatch(r"[0-9a-f]{40}", value) for value in parents)
        )
        require(parents[1] == source)
    identity_check = "tracked-clean"
    git("tracked-clean")
    identity_check = "workflow-blob"
    workflow = git("workflow-blob")
    require(re.fullmatch(r"[0-9a-f]{40}", workflow) is not None)
    identity_check = "run-identity"
    run, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    require(all(re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in (run, attempt)))
    identity_check = "scan-outcome"
    outcome = os.environ["TRIVY_FS_OUTCOME"]
    require(outcome in ("success", "failure"))
    identity_check = "complete"
    return {
        "tested_sha": tested,
        "source_sha": source,
        "workflow_blob": workflow,
        "run_id": run,
        "run_attempt": attempt,
        "scan_outcome": outcome,
    }


def read_report():
    root = Path.cwd().resolve()
    require(root == Path(os.environ["GITHUB_WORKSPACE"]).resolve())
    path = root / "trivy-fs.sarif"
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_BYTES)
        raw = source.read(MAX_BYTES + 1)
        after = os.fstat(source.fileno())
        current = path.lstat()
        stable = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        require(stat.S_ISREG(current.st_mode) and len(raw) == before.st_size)
        require(
            all(
                getattr(before, key) == getattr(after, key) == getattr(current, key)
                for key in stable
            )
        )
        return raw


def self_checks():
    identifier = "CVE-2099-999999"
    message = (
        "Package: fixture-package\nInstalled Version: 1.0.0\nVulnerability "
        + identifier
        + "\nSeverity: HIGH\nFixed Version: 1.0.1\nLink: ["
        + identifier
        + "](https://example.invalid/advisory)"
    )
    fixture = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Trivy",
                        "version": "0.75.0",
                        "rules": [
                            {
                                "id": identifier,
                                "name": "LanguageSpecificPackageVulnerability",
                                "fullDescription": {"text": "PRIVATE_METADATA_CANARY"},
                            }
                        ],
                    }
                },
                "results": [
                    {"ruleId": identifier, "ruleIndex": 0, "message": {"text": message}}
                ],
            }
        ],
    }

    def encode(value):
        return json.dumps(value).encode("utf-8")

    valid = encode(fixture)
    require(
        project(valid)
        == [
            {
                "id": identifier,
                "package": "fixture-package",
                "installed": "1.0.0",
                "fixed": "1.0.1",
                "severity": "HIGH",
            }
        ]
    )
    require("PRIVATE_METADATA_CANARY" not in json.dumps(project(valid)))
    empty = copy.deepcopy(fixture)
    empty["runs"][0]["results"] = []
    empty["runs"][0]["tool"]["driver"]["rules"] = []
    require(project(encode(empty)) == [])
    duplicate = valid.replace(
        b'"version": "2.1.0"', b'"version": "2.1.0", "version": "2.1.0"', 1
    )
    rejected = [b"[]", duplicate, b" " * (MAX_BYTES + 1)]
    bad = copy.deepcopy(fixture)
    bad["runs"][0]["tool"]["driver"]["name"] = "OtherScanner"
    rejected.append(encode(bad))
    bad = copy.deepcopy(fixture)
    nested = None
    for _ in range(25):
        nested = [nested]
    bad["runs"][0]["properties"] = {"nested": nested}
    rejected.append(encode(bad))
    for package in ("fixture##[error]PRIVATE", "fixture\nPRIVATE"):
        bad = copy.deepcopy(fixture)
        bad["runs"][0]["results"][0]["message"]["text"] = message.replace(
            "fixture-package", package
        )
        rejected.append(encode(bad))
    bad = copy.deepcopy(fixture)
    bad["runs"][0]["results"] *= 129
    rejected.append(encode(bad))
    bad = copy.deepcopy(fixture)
    bad["runs"][0]["results"][0]["ruleIndex"] = True
    rejected.append(encode(bad))
    bad = copy.deepcopy(fixture)
    bad["runs"][0]["results"][0]["message"]["text"] = message.replace(
        "Vulnerability " + identifier, "Vulnerability CVE-2099-999998"
    )
    rejected.append(encode(bad))
    bad = copy.deepcopy(fixture)
    bad["runs"][0]["results"][0]["message"]["text"] = (
        "Secret fixture\nMatch: PRIVATE_METADATA_CANARY"
    )
    rejected.append(encode(bad))
    for raw in rejected:
        try:
            project(raw)
        except (ValueError, TypeError, KeyError, IndexError, RecursionError):
            continue
        raise ValueError("parser self-check failed")
    return len(rejected) + 2


stage = "self-checks"
identity_check = "not-started"
try:
    checked = self_checks()
    stage = "identity-before"
    before = identity()
    stage = "read-before"
    raw = read_report()
    stage = "projection"
    records = project(raw)
    stage = "identity-after"
    require(identity() == before)
    stage = "read-after"
    require(read_report() == raw)
    stage = "serialization"
    report = {
        "kind": "temporary-trivy-fs-metadata-not-a-waiver",
        **before,
        "scanner_version": "0.75.0",
        "sarif_sha256": hashlib.sha256(raw).hexdigest(),
        "finding_count": len(records),
        "parser_self_checks": checked,
        "records": records,
    }
    output = (
        PREFIX
        + json.dumps(report, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        + "\n"
    )
    require(len(output.encode("utf-8")) <= 32768)
except (
    OSError,
    UnicodeError,
    ValueError,
    TypeError,
    KeyError,
    IndexError,
    OverflowError,
    RecursionError,
    subprocess.SubprocessError,
):
    check = (
        identity_check
        if stage in ("identity-before", "identity-after")
        else "not-applicable"
    )
    if stage == "identity-before" and check == "tracked-clean":
        try:
            diff = bounded_tracked_diff()
        except Exception:
            diff = None
        if diff is not None:
            print(
                "TRIVY_FS_TRACKED_DIFF "
                + json.dumps(diff, sort_keys=True, separators=(",", ":")),
                file=sys.stderr,
            )
    print(
        "Trivy metadata diagnostic rejected its input (stage="
        + stage
        + "; identity-check="
        + check
        + "); original security gates remain authoritative.",
        file=sys.stderr,
    )
    raise SystemExit(1) from None
sys.stdout.write(output)
