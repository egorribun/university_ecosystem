"""Fail-closed complete-history Gitleaks runner for GitHub Actions."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import stat
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_GIT_TIMEOUT_SECONDS = 10
_MAX_GIT_OUTPUT_BYTES = 1024 * 1024
_TERMINATION_TERM_GRACE_SECONDS = 0.1
_TERMINATION_REAP_TIMEOUT_SECONDS = 1.0
_GITLEAKS_TIMEOUT_SECONDS = 960
_MAX_SARIF_BYTES = 32 * 1024 * 1024
_MAX_DIAGNOSTIC_IDENTITIES = 25
_MAX_DIAGNOSTIC_BYTES = 32 * 1024
_SARIF_RULE_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")
_SARIF_PATH_PATTERN = re.compile(r"[A-Za-z0-9._/-]{1,512}\Z")


class GitleaksGateError(RuntimeError):
    """A closed, non-sensitive failure of the required Gitleaks gate."""


@dataclass(frozen=True, slots=True)
class ScanPlan:
    """Validated GitHub event commits and the exact scanner history range."""

    event_name: str
    base_sha: str
    event_head_sha: str
    git_log_opts: str


def _safe_environment(
    source: Mapping[str, str], git_config_path: Path
) -> dict[str, str]:
    # Git and Gitleaks need executable lookup, a temp location, and locale only.
    # In particular, workflow tokens and application credentials are not inherited.
    allowed = {
        "PATH",
        "HOME",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    env = {
        name: (source[name] if name in source else os.environ[name])
        for name in allowed
        if name in source or name in os.environ
    }
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(git_config_path),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "GIT_LFS_SKIP_SMUDGE": "1",
        }
    )
    return env


@dataclass(frozen=True, slots=True)
class _CommandResult:
    returncode: int
    stdout: str


async def _spawn_and_collect(
    command: list[str],
    environment: Mapping[str, str],
    *,
    timeout_seconds: int,
    max_stdout_bytes: int | None,
    cwd: Path | None = None,
    require_process_group_cleanup: bool = False,
) -> _CommandResult:
    if require_process_group_cleanup and os.name != "posix":
        raise GitleaksGateError("Gitleaks process-group cleanup is unavailable")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    process_options: dict[str, bool] = {}
    if os.name == "posix":
        # Gitleaks starts git as a child; a dedicated session lets timeout cleanup
        # signal the scanner and ordinary descendants as one process group.
        process_options["start_new_session"] = True
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=(
            asyncio.subprocess.PIPE
            if max_stdout_bytes is not None
            else asyncio.subprocess.DEVNULL
        ),
        stderr=asyncio.subprocess.DEVNULL,
        cwd=cwd,
        env=dict(environment),
        **process_options,
    )
    try:
        chunks: list[bytes] = []
        output_size = 0
        if max_stdout_bytes is not None:
            if process.stdout is None:
                raise GitleaksGateError("Git command output could not be captured")
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError
                chunk = await asyncio.wait_for(
                    process.stdout.read(
                        min(64 * 1024, max_stdout_bytes - output_size + 1)
                    ),
                    timeout=remaining,
                )
                if not chunk:
                    break
                output_size += len(chunk)
                if output_size > max_stdout_bytes:
                    raise GitleaksGateError("Git identity output exceeded its limit")
                chunks.append(chunk)
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError
        returncode = await asyncio.wait_for(process.wait(), timeout=remaining)
        return _CommandResult(
            returncode=returncode,
            stdout=b"".join(chunks).decode("utf-8", errors="replace"),
        )
    except BaseException as original_error:
        if not await _terminate_and_reap(process):
            raise GitleaksGateError(
                "Git child cleanup could not be confirmed"
            ) from original_error
        raise


async def _terminate_and_reap(process: asyncio.subprocess.Process) -> bool:
    """Boundedly terminate a child and its ordinary POSIX process-group descendants.

    A process that deliberately detaches from the group is outside this guarantee.
    Windows uses bounded direct-child termination because this runner's required
    hosted environment is POSIX and does not provide a portable group kill here.
    """

    if process.returncode is not None:
        # Once the direct child is reaped its numeric PID may be reused. Do not
        # signal either that PID or its former process-group ID.
        return False

    group_signaling_ok = True
    if os.name == "posix":
        try:
            # Kill the group in one non-yielding operation while the direct
            # child is still owned. A TERM grace would allow that leader to be
            # reaped before a later numeric group signal.
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            group_signaling_ok = False
        except OSError:
            group_signaling_ok = False
    else:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        except OSError:
            group_signaling_ok = False

        await asyncio.sleep(_TERMINATION_TERM_GRACE_SECONDS)
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            except OSError:
                group_signaling_ok = False

    try:
        await asyncio.wait_for(
            process.wait(), timeout=_TERMINATION_REAP_TIMEOUT_SECONDS
        )
    except (OSError, TimeoutError):
        return False
    return process.returncode is not None and group_signaling_ok


def _run_capture(
    command: list[str],
    environment: Mapping[str, str],
    *,
    timeout_seconds: int,
    max_stdout_bytes: int,
) -> _CommandResult:
    try:
        return asyncio.run(
            _spawn_and_collect(
                command,
                environment,
                timeout_seconds=timeout_seconds,
                max_stdout_bytes=max_stdout_bytes,
            )
        )
    except (OSError, TimeoutError) as exc:
        raise GitleaksGateError(
            "Git identity validation could not be completed"
        ) from exc


def _run_silent(
    command: list[str],
    environment: Mapping[str, str],
    *,
    timeout_seconds: int,
    cwd: Path,
) -> _CommandResult:
    try:
        return asyncio.run(
            _spawn_and_collect(
                command,
                environment,
                timeout_seconds=timeout_seconds,
                max_stdout_bytes=None,
                cwd=cwd,
                require_process_group_cleanup=True,
            )
        )
    except (OSError, TimeoutError) as exc:
        raise GitleaksGateError(
            "Gitleaks scan did not complete within its limit"
        ) from exc


def _run_git(
    repository: Path,
    arguments: tuple[str, ...],
    environment: Mapping[str, str],
    *,
    check: bool = True,
) -> _CommandResult:
    result = _run_capture(
        ["git", "-C", str(repository), *arguments],
        environment,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
        max_stdout_bytes=_MAX_GIT_OUTPUT_BYTES,
    )
    if check and result.returncode != 0:
        raise GitleaksGateError("Git identity validation rejected the checkout")
    return result


def _require_sha(value: str | None) -> str:
    if value is None or _SHA_PATTERN.fullmatch(value) is None or value == "0" * 40:
        raise GitleaksGateError("GitHub event commit identity is invalid")
    return value


def _prepare_scan(
    repository: Path,
    event_environment: Mapping[str, str],
    git_environment: Mapping[str, str],
) -> ScanPlan:
    event_name = event_environment.get("GITLEAKS_EVENT_NAME", "")
    if event_name not in {"pull_request", "push"}:
        raise GitleaksGateError("GitHub event type is unsupported")

    try:
        repository = repository.resolve(strict=True)
        event_repository = Path(event_environment["GITHUB_WORKSPACE"]).resolve(
            strict=True
        )
    except (KeyError, OSError, RuntimeError) as exc:
        raise GitleaksGateError("GitHub checkout identity is unavailable") from exc
    if os.path.normcase(str(event_repository)) != os.path.normcase(str(repository)):
        raise GitleaksGateError("GitHub checkout identity does not match the workspace")

    expected_checkout = _require_sha(event_environment.get("GITHUB_SHA"))
    event_head = _require_sha(event_environment.get("GITLEAKS_EVENT_HEAD_SHA"))
    base = _require_sha(event_environment.get("GITLEAKS_BASE_SHA"))

    top_level = _run_git(repository, ("rev-parse", "--show-toplevel"), git_environment)
    try:
        resolved_top_level = Path(top_level.stdout.strip()).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GitleaksGateError("Git checkout root could not be verified") from exc
    if os.path.normcase(str(resolved_top_level)) != os.path.normcase(str(repository)):
        raise GitleaksGateError("Git checkout root does not match the workspace")

    shallow_result = _run_git(
        repository, ("rev-parse", "--is-shallow-repository"), git_environment
    )
    if shallow_result.stdout.strip() != "false":
        raise GitleaksGateError("Git checkout history is shallow and incomplete")

    checkout_result = _run_git(repository, ("rev-parse", "HEAD"), git_environment)
    if checkout_result.stdout.strip() != expected_checkout:
        raise GitleaksGateError("Git checkout commit does not match the event")

    status = _run_git(
        repository,
        ("status", "--porcelain=v1", "--untracked-files=all"),
        git_environment,
    )
    if status.stdout:
        raise GitleaksGateError("Git working tree and index must be clean")

    for commit in (base, event_head, expected_checkout):
        _run_git(
            repository, ("cat-file", "-e", f"{commit}^{{commit}}"), git_environment
        )

    if event_name == "pull_request":
        parent_line = _run_git(
            repository,
            ("rev-list", "--parents", "-n", "1", expected_checkout),
            git_environment,
        ).stdout.split()
        if parent_line != [expected_checkout, base, event_head]:
            raise GitleaksGateError(
                "Pull-request checkout parents do not match the event"
            )

        checkout_tree = _run_git(
            repository, ("rev-parse", f"{expected_checkout}^{{tree}}"), git_environment
        ).stdout.strip()
        event_head_tree = _run_git(
            repository, ("rev-parse", f"{event_head}^{{tree}}"), git_environment
        ).stdout.strip()
        if checkout_tree != event_head_tree:
            raise GitleaksGateError(
                "Pull-request checkout tree differs from the event head; "
                "merge current base into PR branch before scanning"
            )
    else:
        if expected_checkout != event_head:
            raise GitleaksGateError(
                "Push checkout commit does not match the event head"
            )
        ancestry = _run_git(
            repository,
            ("merge-base", "--is-ancestor", base, event_head),
            git_environment,
            check=False,
        )
        if ancestry.returncode != 0:
            raise GitleaksGateError("Push event base is not an ancestor of its head")

    count = _run_git(
        repository, ("rev-list", "--count", f"{base}..{event_head}"), git_environment
    )
    try:
        commit_count = int(count.stdout.strip())
    except ValueError as exc:
        raise GitleaksGateError(
            "GitHub event history range could not be verified"
        ) from exc
    if commit_count <= 0:
        raise GitleaksGateError("GitHub event history range must not be empty")

    return ScanPlan(
        event_name=event_name,
        base_sha=base,
        event_head_sha=event_head,
        git_log_opts=f"{base}..{event_head} --diff-merges=first-parent",
    )


def _git_environment_for(
    repository: Path,
    source_environment: Mapping[str, str],
) -> tuple[tempfile.TemporaryDirectory[str], dict[str, str]]:
    temporary = tempfile.TemporaryDirectory(prefix="gitleaks-git-config-")
    temporary_path = Path(temporary.name).resolve(strict=True)
    if temporary_path.is_relative_to(repository.resolve(strict=True)):
        temporary.cleanup()
        raise GitleaksGateError("Git isolation directory must be outside the checkout")
    global_config = temporary_path / "empty.gitconfig"
    global_config.write_text("", encoding="utf-8")
    return temporary, _safe_environment(source_environment, global_config)


def prepare_scan(
    repository: Path,
    event_environment: Mapping[str, str],
) -> ScanPlan:
    """Validate event, checkout, and graph identity before any scanner invocation."""

    try:
        resolved_repository = repository.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GitleaksGateError("GitHub checkout identity is unavailable") from exc
    temporary, git_environment = _git_environment_for(
        resolved_repository, event_environment
    )
    try:
        return _prepare_scan(resolved_repository, event_environment, git_environment)
    finally:
        temporary.cleanup()


def build_gitleaks_command(
    binary: Path,
    repository: Path,
    plan: ScanPlan,
    report_path: Path,
) -> list[str]:
    """Build the explicit redacted SARIF command for a validated event range."""

    try:
        resolved_repository = repository.resolve(strict=True)
        resolved_report = report_path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise GitleaksGateError(
            "Gitleaks output location could not be verified"
        ) from exc
    if not report_path.is_absolute() or resolved_report.is_relative_to(
        resolved_repository
    ):
        raise GitleaksGateError("Redacted SARIF must be written outside the checkout")
    if not Path(binary).is_absolute():
        raise GitleaksGateError("Gitleaks executable path must be absolute")
    base = _require_sha(plan.base_sha)
    event_head = _require_sha(plan.event_head_sha)
    expected_log_opts = f"{base}..{event_head} --diff-merges=first-parent"
    if (
        plan.event_name not in {"pull_request", "push"}
        or plan.git_log_opts != expected_log_opts
    ):
        raise GitleaksGateError("Gitleaks history range is not a validated plan")
    return [
        str(binary),
        "git",
        "--config",
        str(resolved_repository / ".gitleaks.toml"),
        "--redact=100",
        "--exit-code=2",
        "--report-format=sarif",
        f"--report-path={resolved_report}",
        "--log-level=error",
        "--timeout=900",
        "--log-opts",
        plan.git_log_opts,
        str(resolved_repository),
    ]


def _sarif_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise GitleaksGateError("Redacted SARIF report metadata is invalid")
    return value


def _sarif_identity(result: object) -> dict[str, str | int]:
    """Select only finite identity fields from the pinned scanner's SARIF shape."""

    finding = _sarif_object(result)
    rule_id = finding.get("ruleId")
    if not isinstance(rule_id, str) or _SARIF_RULE_PATTERN.fullmatch(rule_id) is None:
        raise GitleaksGateError("Redacted SARIF rule identity is invalid")

    locations = finding.get("locations")
    if not isinstance(locations, list) or len(locations) != 1:
        raise GitleaksGateError("Redacted SARIF location topology is unsupported")
    location = _sarif_object(locations[0])
    physical_location = _sarif_object(location.get("physicalLocation"))
    artifact_location = _sarif_object(physical_location.get("artifactLocation"))
    region = _sarif_object(physical_location.get("region"))
    path = artifact_location.get("uri")
    if (
        not isinstance(path, str)
        or _SARIF_PATH_PATTERN.fullmatch(path) is None
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise GitleaksGateError("Redacted SARIF path identity is invalid")
    line = region.get("startLine")
    if not isinstance(line, int) or isinstance(line, bool) or not 1 <= line < 2**31:
        raise GitleaksGateError("Redacted SARIF line identity is invalid")

    identity: dict[str, str | int] = {
        "rule_id": rule_id,
        "path": path,
        "line": line,
    }
    fingerprints = _sarif_object(finding.get("partialFingerprints", {}))
    commit = fingerprints.get("commitSha", "")
    if not isinstance(commit, str):
        raise GitleaksGateError("Redacted SARIF commit identity is invalid")
    if commit:
        identity["commit"] = _require_sha(commit)
    return identity


def _validate_sarif(
    report_path: Path,
) -> tuple[int, list[dict[str, str | int]]]:
    try:
        metadata = report_path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_SARIF_BYTES:
            raise GitleaksGateError("Redacted SARIF report is unavailable or oversized")
        report = json.loads(report_path.read_bytes())
    except GitleaksGateError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise GitleaksGateError("Redacted SARIF report is invalid") from exc
    if not isinstance(report, dict) or report.get("version") != "2.1.0":
        raise GitleaksGateError("Redacted SARIF report is invalid")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) != 1:
        raise GitleaksGateError("Redacted SARIF run topology is unsupported")
    results = _sarif_object(runs[0]).get("results")
    if not isinstance(results, list):
        raise GitleaksGateError("Redacted SARIF result metadata is invalid")

    identities: list[dict[str, str | int]] = []
    for result in results:
        # Validate every identity before logging anything, including those beyond
        # the output cap. No snippets, messages or arbitrary metadata are copied.
        identity = _sarif_identity(result)
        if len(identities) < _MAX_DIAGNOSTIC_IDENTITIES:
            identities.append(identity)
    return len(results), identities


def execute_scan(
    event_environment: Mapping[str, str],
) -> int:
    """Validate immutable history and emit only a bounded identity summary."""

    workspace = event_environment.get("GITHUB_WORKSPACE", "")
    report_value = event_environment.get("GITLEAKS_REPORT_PATH", "")
    binary_value = event_environment.get("GITLEAKS_BIN", "")
    if not workspace or not report_value or not binary_value:
        raise GitleaksGateError("Gitleaks runner configuration is incomplete")
    repository = Path(workspace)
    report_path = Path(report_value)
    if not report_path.is_absolute():
        raise GitleaksGateError("Redacted SARIF path must be absolute")

    try:
        resolved_repository = repository.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GitleaksGateError("GitHub checkout identity is unavailable") from exc
    temporary, git_environment = _git_environment_for(
        resolved_repository, event_environment
    )
    try:
        plan = _prepare_scan(resolved_repository, event_environment, git_environment)
        command = build_gitleaks_command(
            Path(binary_value), resolved_repository, plan, report_path
        )
        resolved_report = report_path.resolve(strict=False)
        try:
            resolved_report.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise GitleaksGateError(
                "Redacted SARIF output directory is unavailable"
            ) from exc
        scan_environment = dict(git_environment)
        result = _run_silent(
            command,
            scan_environment,
            timeout_seconds=_GITLEAKS_TIMEOUT_SECONDS,
            cwd=resolved_repository,
        )
        if result.returncode not in {0, 2}:
            raise GitleaksGateError("Gitleaks scan failed")
        result_count, identities = _validate_sarif(resolved_report)
        if result.returncode == 0 and result_count:
            raise GitleaksGateError("Gitleaks status contradicts its report")
        summary = {
            "status": "findings" if result.returncode == 2 else "clean",
            "scanner_exit_code": result.returncode,
            "result_count": result_count,
            "identities": identities,
            "omitted_identity_count": result_count - len(identities),
        }
        diagnostic = "GITLEAKS_DIAGNOSTIC " + json.dumps(
            summary, ensure_ascii=True, separators=(",", ":")
        )
        if len(diagnostic.encode("ascii")) + 1 > _MAX_DIAGNOSTIC_BYTES:
            raise GitleaksGateError("Gitleaks diagnostic exceeded its output limit")
        print(diagnostic)
        return result.returncode
    finally:
        temporary.cleanup()


def main() -> int:
    try:
        return execute_scan(os.environ)
    except GitleaksGateError:
        print('GITLEAKS_DIAGNOSTIC {"status":"gate_error"}', file=sys.stderr)
        print(
            "Gitleaks gate failed closed; see the redacted SARIF artifact if available.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
