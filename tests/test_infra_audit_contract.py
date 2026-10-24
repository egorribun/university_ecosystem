"""Regression contracts for the independently audited infrastructure fixes."""

from __future__ import annotations

import ntpath
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/university-ecosystem"


def _windows_bash_path(path: str) -> str:
    drive, tail = ntpath.splitdrive(path)
    if len(drive) != 2 or drive[1] != ":":
        return Path(path).as_posix()
    return f"/{drive[0].lower()}{tail.replace(chr(92), '/')}"


def _bash_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt":
        return Path(resolved).as_posix()
    return _windows_bash_path(resolved)


def _bash_candidates() -> list[str]:
    if os.name != "nt":
        bash = shutil.which("bash")
        return [bash] if bash else []

    candidates: list[Path] = []
    git = shutil.which("git")
    if git:
        git_command_dir = Path(git).resolve().parent
        candidates.extend(
            (
                git_command_dir / "bash.exe",
                git_command_dir.parent / "bin" / "bash.exe",
            )
        )
    for variable in ("ProgramFiles", "ProgramW6432"):
        program_files = os.environ.get(variable)
        if program_files:
            candidates.append(Path(program_files) / "Git" / "bin" / "bash.exe")
    local_programs = os.environ.get("LOCALAPPDATA")
    if local_programs:
        candidates.append(
            Path(local_programs) / "Programs" / "Git" / "bin" / "bash.exe"
        )
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            candidates.extend((Path(entry) / "bash.exe", Path(entry) / "bash"))

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.is_file():
            continue
        resolved = str(candidate.resolve())
        key = os.path.normcase(resolved)
        if key not in seen:
            unique.append(resolved)
            seen.add(key)
    return unique


def _find_compatible_bash(candidates: list[str] | None = None) -> str | None:
    launched = False
    for bash in _bash_candidates() if candidates is None else candidates:
        try:
            launch_probe = subprocess.run(  # noqa: S603 - fixed host-shell probe
                [bash, "-c", "exit 0"],
                check=False,
                capture_output=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if launch_probe.returncode != 0:
            continue

        launched = True
        try:
            path_probe = subprocess.run(  # noqa: S603 - fixed host-path probe
                [
                    bash,
                    "-c",
                    'test -f "$1" && test -x "$2"',
                    "--",
                    _bash_path(ROOT / "scripts/apply_raw_k8s.sh"),
                    _bash_path(Path(sys.executable)),
                ],
                check=False,
                capture_output=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if path_probe.returncode == 0:
            return bash

    if launched:
        raise RuntimeError(
            "a Bash executable launched but could not access host paths using "
            "the selected path mapping"
        )
    return None


def test_helm_frontend_and_gateway_have_bounded_autoscaling_contracts() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    staging = yaml.safe_load(
        (CHART / "values-staging.yaml").read_text(encoding="utf-8")
    )

    assert values["frontend"]["resources"]["limits"]["memory"] == "512Mi"
    for component in ("frontend", "gateway"):
        autoscaling = values[component]["autoscaling"]
        assert autoscaling == {
            "enabled": False,
            "minReplicas": 2,
            "maxReplicas": 8,
            "targetCPUUtilizationPercentage": 70,
            "targetMemoryUtilizationPercentage": 80,
        }
        staging_autoscaling = staging[component]["autoscaling"]
        assert staging_autoscaling["enabled"] is True
        assert staging_autoscaling["minReplicas"] >= 2
        assert staging_autoscaling["maxReplicas"] >= staging_autoscaling["minReplicas"]


def test_helm_hpas_target_matching_deployments_and_avoid_keda_conflicts() -> None:
    for component in ("frontend", "gateway"):
        template = (CHART / "templates" / f"{component}-hpa.yaml").read_text(
            encoding="utf-8"
        )
        deployment = (CHART / "templates" / f"{component}-deployment.yaml").read_text(
            encoding="utf-8"
        )
        assert "apiVersion: autoscaling/v2" in template
        assert "kind: HorizontalPodAutoscaler" in template
        assert f".Values.{component}.autoscaling" in template
        assert (
            f'name: {{{{ include "university-ecosystem.fullname" . }}}}-{component}'
            in template
        )
        assert ".Values.keda.enabled" in template
        assert f".Values.{component}.autoscaling.enabled" in deployment


def test_backend_image_and_go_overlay_use_readiness_probes() -> None:
    dockerfile = (ROOT / "backend.Dockerfile").read_text(encoding="utf-8")
    assert "127.0.0.1:8000/health/ready" in dockerfile
    assert "127.0.0.1:8000/healthz" not in dockerfile

    compose = yaml.safe_load(
        (ROOT / "docker-compose.go.yml").read_text(encoding="utf-8")
    )
    healthcheck = compose["services"]["file-processor"]["healthcheck"]
    assert healthcheck["test"] == [
        "CMD",
        "/usr/local/bin/grpc_health_probe",
        "-addr=:50051",
    ]


def test_observability_override_defines_tempo_healthprobe() -> None:
    source = (ROOT / "docker-compose.observability.yml").read_text(encoding="utf-8")
    marker = "  tempo-healthprobe:\n"
    assert marker in source
    probe = source[source.index(marker) :]
    assert 'network_mode: "service:tempo"' in probe
    assert "http://localhost:3200/ready" in probe
    assert "curlimages/curl:8.22.0@sha256:" in probe


def test_standalone_ingress_requires_explicit_certificate_issuer() -> None:
    source = (ROOT / "k8s/ingress.yaml").read_text(encoding="utf-8")
    assert 'cert-manager.io/cluster-issuer: "${CERT_MANAGER_ISSUER_NAME}"' in source
    assert 'cert-manager.io/cluster-issuer: "letsencrypt-prod"' not in source
    assert "CERT_MANAGER_ISSUER_NAME" in source


def test_raw_manifest_wrapper_is_allowlisted_and_fail_closed() -> None:
    """Raw parameterized manifests must have one reviewed, safe entrypoint.

    The Helm chart is the release artifact.  This contract protects the small
    set of supporting manifests that still use ``envsubst`` from being applied
    with an empty or mutable image value, or from turning an arbitrary path
    supplied by a shell caller into a deployment primitive.
    """

    wrapper = (ROOT / "scripts/apply_raw_k8s.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in wrapper
    assert 'manifest="${1:-}"' in wrapper
    assert '[[ "$#" -eq 1 ]]' in wrapper
    assert 'envsubst "$substitution_set"' in wrapper
    assert "kubectl apply -f -" in wrapper
    assert "k8s/ingress.yaml" in wrapper
    assert "k8s/backend/secret-store.yaml" in wrapper
    assert "k8s/backend/deployment.yaml" in wrapper
    assert "k8s/frontend/deployment.yaml" in wrapper
    assert "IMAGE_TAG" in wrapper
    assert "IMAGE_REGISTRY" in wrapper
    assert "^[0-9a-fA-F]{40}$" in wrapper
    assert (
        "^[[:space:]-]*image:[[:space:]]*[^[:space:]]+:(latest)?([[:space:]]|#|$)"
        in wrapper
    )
    assert "unresolved template variable" in wrapper
    assert "unsupported raw manifest" in wrapper
    assert "registry.example.com" not in wrapper

    readme = (ROOT / "k8s/README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split()).lower()
    assert "apply_raw_k8s.sh" in normalized
    assert "image_tag" in normalized
    assert "commit sha or semver" in normalized


def test_raw_manifest_wrapper_renders_and_rejects_mutable_images(
    tmp_path: Path,
) -> None:
    """Exercise the wrapper with hermetic envsubst/kubectl stand-ins through Bash."""

    bash = _find_compatible_bash()
    if not bash:
        # INFRA-03 @egorribun: Linux shell contract is exercised in CI.
        pytest.skip("bash is unavailable on this host")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "kubectl-input.yaml"

    def write_python_stub(name: str, source: str) -> None:
        script = bin_dir / f"{name}.py"
        script.write_text(source, encoding="utf-8")
        executable = bin_dir / name
        executable.write_text(
            "#!/usr/bin/env bash\n"
            f"exec {shlex.quote(_bash_path(Path(sys.executable)))} "
            f'{shlex.quote(_bash_path(script))} "$@"\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)

    write_python_stub(
        "envsubst",
        "import os, sys\n"
        "value = sys.stdin.read()\n"
        "for name in ('IMAGE_REGISTRY', 'IMAGE_TAG', 'CERT_MANAGER_ISSUER_NAME', 'FRONTEND_HOST', 'API_HOST', 'TLS_SECRET_NAME', 'VAULT_URL'):\n"
        "    value = value.replace('${' + name + '}', os.environ.get(name, ''))\n"
        "    value = value.replace('$' + name, os.environ.get(name, ''))\n"
        "sys.stdout.write(value)\n",
    )
    write_python_stub(
        "kubectl",
        "import os, pathlib, sys\n"
        "if sys.argv[1:] != ['apply', '-f', '-']:\n"
        "    raise SystemExit(2)\n"
        "pathlib.Path(os.environ['KUBECTL_CAPTURE']).write_text(sys.stdin.read(), encoding='utf-8')\n",
    )

    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join((str(bin_dir), environment["PATH"]))
    environment["KUBECTL_CAPTURE"] = str(capture)
    environment["IMAGE_REGISTRY"] = "registry.example.com"
    environment["IMAGE_TAG"] = "0" * 40
    valid = subprocess.run(  # noqa: S603 - fixed local wrapper invocation
        [bash, str(ROOT / "scripts/apply_raw_k8s.sh"), "k8s/backend/deployment.yaml"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert valid.returncode == 0, valid.stderr
    rendered = capture.read_text(encoding="utf-8")
    assert "${IMAGE_TAG}" not in rendered
    assert f"registry.example.com/backend:{'0' * 40}" in rendered

    capture.unlink()
    environment["IMAGE_TAG"] = "latest"
    rejected = subprocess.run(  # noqa: S603 - fixed local wrapper invocation
        [bash, str(ROOT / "scripts/apply_raw_k8s.sh"), "k8s/backend/deployment.yaml"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert rejected.returncode != 0
    assert "semantic version" in rejected.stderr
    assert not capture.exists()


def test_raw_k8s_scope_declares_helm_as_canonical_application_producer() -> None:
    """Keep the raw-manifest scope and the Helm workload inventory aligned.

    The standalone tree intentionally omits the Go workloads.  This contract
    prevents a future documentation edit from presenting the partial raw
    bundle as a production deployment, while also making additions to the
    chart's first-party workload set visible in the canonical-owner guidance.
    """

    readme = (ROOT / "k8s/README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split()).lower()

    assert "sole canonical producer" in normalized
    assert "single canonical deployment artifact" in normalized
    assert "must not be used as a staging or production release path" in normalized
    assert "does not duplicate the go service deployments or services" in normalized

    deployment_templates = sorted(
        path.stem.removesuffix("-deployment")
        for path in (CHART / "templates").glob("*-deployment.yaml")
    )
    assert deployment_templates == [
        "backend",
        "file-processor",
        "frontend",
        "gateway",
        "outbox-worker",
        "ws-hub",
    ]
    for component in deployment_templates:
        assert f"`{component}`" in readme

    for component in ("gateway", "ws-hub", "file-processor"):
        assert not list((ROOT / "k8s").rglob(f"{component}*deployment*.yaml"))


def test_helm_canonical_scope_is_recorded_in_adr_index() -> None:
    """The INFRA-02 scope decision must be durable and discoverable."""

    adr_path = ROOT / "docs/adr/ADR-034-helm-canonical-application-deployment.md"
    index_path = ROOT / "docs/adr/README.md"
    assert adr_path.is_file()
    adr = adr_path.read_text(encoding="utf-8")
    normalized = adr.lower()
    assert "status" in normalized and "accepted" in normalized
    for heading in (
        "## context",
        "## considered options",
        "## decision",
        "## consequences",
    ):
        assert heading in normalized
    assert "sole canonical producer" in normalized
    assert "raw k8s" in normalized
    index = index_path.read_text(encoding="utf-8")
    assert "ADR-034" in index
    assert "Helm" in index


def test_windows_bash_path_mapping_uses_git_drive_syntax() -> None:
    assert (
        _windows_bash_path(r"C:\Program Files\Git\bin\bash.exe")
        == "/c/Program Files/Git/bin/bash.exe"
    )


def test_compatible_bash_selection_uses_next_candidate_after_path_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = ["wsl-bash", "git-bash"]
    calls: list[tuple[list[str], int | None]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        timeout = kwargs.get("timeout")
        calls.append((command, timeout if isinstance(timeout, int) else None))
        if command[2] == "exit 0":
            return subprocess.CompletedProcess(command, 0)
        return subprocess.CompletedProcess(
            command, 1 if command[0] == "wsl-bash" else 0
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _find_compatible_bash(candidates) == "git-bash"
    assert [(command[0], command[2]) for command, _ in calls] == [
        ("wsl-bash", "exit 0"),
        ("wsl-bash", 'test -f "$1" && test -x "$2"'),
        ("git-bash", "exit 0"),
        ("git-bash", 'test -f "$1" && test -x "$2"'),
    ]
    assert all(timeout == 3 for _, timeout in calls)
    path_probe = calls[1][0]
    assert path_probe[4] == _bash_path(ROOT / "scripts/apply_raw_k8s.sh")
    assert path_probe[5] == _bash_path(Path(sys.executable))


def test_compatible_bash_selection_returns_none_when_no_bash_can_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], int | None]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        timeout = kwargs.get("timeout")
        calls.append((command, timeout if isinstance(timeout, int) else None))
        if command[0] == "unlaunchable-bash":
            raise OSError("not executable")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _find_compatible_bash(["unlaunchable-bash", "not-bash"]) is None
    assert len(calls) == 2
    assert all(command[2] == "exit 0" for command, _ in calls)
    assert all(timeout == 3 for _, timeout in calls)


def test_compatible_bash_selection_fails_when_launched_bash_cannot_access_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], int | None]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        timeout = kwargs.get("timeout")
        calls.append((command, timeout if isinstance(timeout, int) else None))
        return subprocess.CompletedProcess(command, 0 if command[2] == "exit 0" else 1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="launched but could not access"):
        _find_compatible_bash(["path-incompatible-bash"])
    assert [command[2] for command, _ in calls] == [
        "exit 0",
        'test -f "$1" && test -x "$2"',
    ]
    assert all(timeout == 3 for _, timeout in calls)
