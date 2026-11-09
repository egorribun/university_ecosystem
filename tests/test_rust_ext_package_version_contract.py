"""Keep static Python metadata aligned with the native crate version."""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _assert_version_parity(python_project: dict, cargo_package: dict) -> None:
    assert "version" not in python_project.get("dynamic", [])
    version = python_project.get("version")
    assert isinstance(version, str) and version
    assert version == cargo_package["version"]


def test_native_python_and_cargo_versions_match() -> None:
    native = ROOT / "native" / "rust_ext"
    python_project = tomllib.loads((native / "pyproject.toml").read_text())["project"]
    cargo_package = tomllib.loads((native / "Cargo.toml").read_text())["package"]
    _assert_version_parity(python_project, cargo_package)


@pytest.mark.parametrize(
    "python_project",
    [
        {},
        {"version": ""},
        {"version": 1},
        {"version": "0.2.0"},
        {"version": "0.1.0", "dynamic": ["version"]},
    ],
)
def test_native_version_contract_rejects_drift(python_project: dict) -> None:
    with pytest.raises(AssertionError):
        _assert_version_parity(python_project, {"version": "0.1.0"})
