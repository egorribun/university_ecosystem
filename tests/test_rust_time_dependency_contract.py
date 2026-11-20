"""Keep the native date dependency graph and advisory retirement aligned."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native" / "rust_ext"


def _read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_native_and_fuzz_lockfiles_share_time_without_chrono() -> None:
    manifest = _read_toml(NATIVE / "Cargo.toml")
    deps = manifest["dependencies"]
    assert "chrono" not in deps
    assert "chrono" not in deps["pyo3"]["features"]
    assert "time" in deps["pyo3"]["features"]
    assert "time" in deps

    pyo3_dependencies = {
        "pyo3",
        "pyo3-build-config",
        "pyo3-ffi",
        "pyo3-macros",
        "pyo3-macros-backend",
    }
    time_dependencies = {"time", "time-core", "time-macros"}
    shared_dependencies = pyo3_dependencies | time_dependencies
    versions_by_lock = []
    for path in (NATIVE / "Cargo.lock", NATIVE / "fuzz" / "Cargo.lock"):
        packages = _read_toml(path)["package"]
        assert not any(package["name"] == "chrono" for package in packages), path
        versions = {}
        for package in packages:
            name = package["name"]
            if name in shared_dependencies:
                assert name not in versions, (path, name)
                versions[name] = package["version"]
            if name == "pyo3":
                assert "time" in package["dependencies"]
                assert "chrono" not in package["dependencies"]
        assert set(versions) == shared_dependencies, path
        assert all(versions[name] == versions["pyo3"] for name in pyo3_dependencies)
        versions_by_lock.append({name: versions[name] for name in time_dependencies})
    assert versions_by_lock[0] == versions_by_lock[1]


def test_chrono_advisory_exception_is_retired() -> None:
    advisory = _read_toml(NATIVE / "deny.toml")["advisories"]
    assert all(
        entry.get("id") != "RUSTSEC-2026-0543" for entry in advisory.get("ignore", [])
    )
