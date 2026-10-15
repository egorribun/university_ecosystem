"""Guard compatible OTLP package metadata and runtime imports."""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import distribution, version

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_OTLP_RELEASE_FAMILY = (
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp",
    "opentelemetry-exporter-otlp-proto-grpc",
    "opentelemetry-exporter-otlp-proto-http",
    "opentelemetry-exporter-otlp-proto-common",
    "opentelemetry-proto",
)

_REQUIRED_OTLP_METADATA_EDGES = {
    "opentelemetry-sdk": ("opentelemetry-api",),
    "opentelemetry-exporter-otlp": (
        "opentelemetry-exporter-otlp-proto-grpc",
        "opentelemetry-exporter-otlp-proto-http",
    ),
    "opentelemetry-exporter-otlp-proto-grpc": (
        "opentelemetry-api",
        "opentelemetry-sdk",
        "opentelemetry-exporter-otlp-proto-common",
        "opentelemetry-proto",
    ),
    "opentelemetry-exporter-otlp-proto-http": (
        "opentelemetry-api",
        "opentelemetry-sdk",
        "opentelemetry-exporter-otlp-proto-common",
        "opentelemetry-proto",
    ),
    "opentelemetry-exporter-otlp-proto-common": ("opentelemetry-proto",),
}


def test_otlp_release_family_is_aligned_and_metadata_compatible() -> None:
    installed_versions = {package: version(package) for package in _OTLP_RELEASE_FAMILY}
    api_version = installed_versions["opentelemetry-api"]

    assert all(installed == api_version for installed in installed_versions.values())

    for package, dependency_names in _REQUIRED_OTLP_METADATA_EDGES.items():
        requirements = [
            Requirement(raw_requirement)
            for raw_requirement in distribution(package).metadata.get_all(
                "Requires-Dist"
            )
            or ()
        ]
        for dependency_name in dependency_names:
            canonical_dependency = canonicalize_name(dependency_name)
            active_matches = [
                requirement
                for requirement in requirements
                if canonicalize_name(requirement.name) == canonical_dependency
                and (requirement.marker is None or requirement.marker.evaluate())
            ]

            assert len(active_matches) == 1, (
                f"{package} must declare one active Requires-Dist for {dependency_name}"
            )
            assert installed_versions[dependency_name] in active_matches[0].specifier, (
                f"{package} metadata does not permit the installed "
                f"{dependency_name} version {installed_versions[dependency_name]}"
            )


def test_otlp_exporter_and_application_observability_imports() -> None:
    from app.core import observability

    for module_name in (
        "opentelemetry.exporter.otlp.proto.common._internal",
        "opentelemetry.exporter.otlp.proto.grpc._log_exporter",
        "opentelemetry.exporter.otlp.proto.grpc.metric_exporter",
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        "opentelemetry.exporter.otlp.proto.http._log_exporter",
        "app.core.observability",
    ):
        imported_module = import_module(module_name)
        if module_name == "app.core.observability":
            assert imported_module is observability
