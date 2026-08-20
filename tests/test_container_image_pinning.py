"""Supply-chain contracts for immutable external container references."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "k8s").exists():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = _find_repo_root()
_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
_YAML_IMAGE_RE = re.compile(r"^\s*image:\s*['\"]?([^\s#'\"]+)", re.MULTILINE)


def _assert_digest_pinned(references: list[tuple[Path, str]]) -> None:
    unpinned = [
        f"{path.relative_to(ROOT)}: {reference}"
        for path, reference in references
        if not _DIGEST_RE.search(reference)
    ]
    assert not unpinned, "Mutable external container references:\n" + "\n".join(
        unpinned
    )


def test_all_static_compose_images_are_digest_pinned() -> None:
    references: list[tuple[Path, str]] = []
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        for reference in _YAML_IMAGE_RE.findall(path.read_text(encoding="utf-8")):
            if "$" not in reference:
                references.append((path, reference))

    assert references, "No static Compose image references were discovered"
    _assert_digest_pinned(references)


def test_all_external_dockerfile_stages_are_digest_pinned() -> None:
    references: list[tuple[Path, str]] = []
    paths = [
        *ROOT.glob("Dockerfile*"),
        *(ROOT / ".containers").rglob("Dockerfile*"),
        *(ROOT / "infra").rglob("Dockerfile*"),
        *(ROOT / "services").rglob("Dockerfile*"),
    ]
    for path in sorted(paths):
        stage_aliases: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*FROM\s+(\S+)(?:\s+AS\s+(\S+))?", line, re.IGNORECASE)
            if match is None:
                continue
            reference, alias = match.groups()
            if reference not in stage_aliases and "$" not in reference:
                references.append((path, reference))
            if alias:
                stage_aliases.add(alias)

    assert references, "No external Dockerfile stages were discovered"
    _assert_digest_pinned(references)


def test_static_kubernetes_images_are_digest_pinned() -> None:
    references: list[tuple[Path, str]] = []
    for path in sorted((ROOT / "k8s").rglob("*.yaml")):
        if "tests" in path.parts:
            continue
        for reference in _YAML_IMAGE_RE.findall(path.read_text(encoding="utf-8")):
            if "$" not in reference and "{{" not in reference and "*" not in reference:
                references.append((path, reference))

    assert references, "No static Kubernetes image references were discovered"
    _assert_digest_pinned(references)


@pytest.mark.parametrize(
    "path,pattern",
    [
        (
            ROOT / "tests" / "conftest.py",
            re.compile(
                r'(?:DockerContainer|PostgresContainer|RedisContainer)\(\s*["\']([^"\']+)',
                re.DOTALL,
            ),
        ),
        *[
            (
                path,
                re.compile(
                    r'(?:DockerContainer|PostgresContainer|RedisContainer)\(\s*["\']([^"\']+)',
                    re.DOTALL,
                ),
            )
            for path in sorted((ROOT / "tests" / "integration").glob("*.py"))
        ],
        *[
            (
                path,
                re.compile(
                    r'(?:tcnats|tcredis|tcminio)\.Run\(\s*[^,]+,\s*["\']([^"\']+)',
                    re.DOTALL,
                ),
            )
            for path in sorted((ROOT / "services").rglob("*_integration_test.go"))
        ],
    ],
    ids=lambda value: str(value.relative_to(ROOT)) if isinstance(value, Path) else None,
)
def test_testcontainer_images_are_digest_pinned(
    path: Path, pattern: re.Pattern[str]
) -> None:
    references = pattern.findall(path.read_text(encoding="utf-8"))
    if references:
        _assert_digest_pinned([(path, reference) for reference in references])


@pytest.mark.parametrize(
    "path,image_prefix",
    [
        (
            ROOT / "scripts" / "run-docker-visual-tests.sh",
            "mcr.microsoft.com/playwright:v1.58.2-noble",
        ),
        (
            ROOT / "scripts" / "run-docker-visual-tests.ps1",
            "mcr.microsoft.com/playwright:v1.58.2-noble",
        ),
        (ROOT / "start-docker.ps1", "alpine:3.20"),
    ],
)
def test_scripted_external_images_are_digest_pinned(
    path: Path, image_prefix: str
) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(image_prefix)}@sha256:[0-9a-f]{{64}}", text)
    assert match is not None, (
        f"{path.relative_to(ROOT)} does not pin {image_prefix} by digest"
    )


def test_helm_backup_images_are_digest_pinned() -> None:
    values = (ROOT / "charts" / "university-ecosystem" / "values.yaml").read_text(
        encoding="utf-8"
    )
    references = re.findall(
        r'^\s*(?:postgresImage|minioClientImage):\s*["\']([^"\']+)',
        values,
        re.MULTILINE,
    )
    assert len(references) == 2
    _assert_digest_pinned(
        [
            (ROOT / "charts" / "university-ecosystem" / "values.yaml", reference)
            for reference in references
        ]
    )
