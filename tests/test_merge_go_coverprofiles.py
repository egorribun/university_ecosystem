from pathlib import Path

import pytest

from scripts.quality.merge_go_coverprofiles import ProfileError, merge_profiles


def _profile(path: Path, *records: str, mode: str = "atomic") -> Path:
    path.write_text(
        "\n".join((f"mode: {mode}", *records, "")),
        encoding="utf-8",
    )
    return path


def test_merge_profiles_writes_one_header_and_all_disjoint_records(
    tmp_path: Path,
) -> None:
    first = _profile(tmp_path / "first.out", "one.go:1.1,2.1 1 1")
    second = _profile(tmp_path / "second.out", "two.go:3.1,4.1 2 0")
    output = tmp_path / "merged.out"

    merge_profiles((first, second), output)

    assert output.read_text(encoding="utf-8") == (
        "mode: atomic\none.go:1.1,2.1 1 1\ntwo.go:3.1,4.1 2 0\n"
    )


@pytest.mark.parametrize(
    ("contents", "message"),
    (
        ("", "is empty"),
        ("not-a-profile\n", "invalid coverage mode"),
        ("mode: atomic\nbroken\n", "malformed coverage record"),
        ("mode: atomic\none.go:1.1,2.1 -1 1\n", "negative statement count"),
        ("mode: atomic\none.go:1.1,2.1 1 -1\n", "negative execution count"),
    ),
)
def test_merge_profiles_rejects_malformed_input(
    tmp_path: Path,
    contents: str,
    message: str,
) -> None:
    profile = tmp_path / "invalid.out"
    profile.write_text(contents, encoding="utf-8")

    with pytest.raises(ProfileError, match=message):
        merge_profiles((profile,), tmp_path / "merged.out")


def test_merge_profiles_rejects_mixed_modes(tmp_path: Path) -> None:
    first = _profile(tmp_path / "first.out", "one.go:1.1,2.1 1 1")
    second = _profile(
        tmp_path / "second.out",
        "two.go:1.1,2.1 1 1",
        mode="count",
    )

    with pytest.raises(ProfileError, match="coverage mode mismatch"):
        merge_profiles((first, second), tmp_path / "merged.out")


def test_merge_profiles_rejects_duplicate_blocks(tmp_path: Path) -> None:
    record = "one.go:1.1,2.1 1 1"
    first = _profile(tmp_path / "first.out", record)
    second = _profile(tmp_path / "second.out", record)

    with pytest.raises(ProfileError, match="duplicate coverage block"):
        merge_profiles((first, second), tmp_path / "merged.out")


def test_merge_profiles_requires_input_and_distinct_output(tmp_path: Path) -> None:
    output = tmp_path / "merged.out"
    with pytest.raises(ProfileError, match="at least one input"):
        merge_profiles((), output)

    profile = _profile(tmp_path / "source.out", "one.go:1.1,2.1 1 1")
    with pytest.raises(ProfileError, match="must differ"):
        merge_profiles((profile,), profile)
