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


@pytest.mark.parametrize("mode", ["set", "count", "atomic"])
@pytest.mark.parametrize("same_profile", [False, True])
def test_merge_profiles_rejects_conflicting_statement_counts(
    tmp_path: Path, mode: str, same_profile: bool
) -> None:
    first_record = "source directory/one.go:1.1,2.1 1 1"
    conflicting_record = "source directory/one.go:1.1,2.1 2 0"
    if same_profile:
        inputs = (
            _profile(
                tmp_path / "first.out",
                first_record,
                conflicting_record,
                mode=mode,
            ),
        )
    else:
        inputs = (
            _profile(tmp_path / "first.out", first_record, mode=mode),
            _profile(tmp_path / "second.out", conflicting_record, mode=mode),
        )
    output = tmp_path / "merged.out"
    output.write_text("previous verified output\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="duplicate coverage block"):
        merge_profiles(inputs, output)

    assert output.read_text(encoding="utf-8") == "previous verified output\n"


def test_merge_profiles_keeps_distinct_ranges_in_same_file(tmp_path: Path) -> None:
    records = (
        "source directory/one.go:1.1,2.1 1 1",
        "source directory/one.go:3.1,4.1 2 0",
    )
    first = _profile(tmp_path / "first.out", records[0])
    second = _profile(tmp_path / "second.out", records[1])
    output = tmp_path / "merged.out"

    merge_profiles((first, second), output)

    assert output.read_text(encoding="utf-8") == (
        "mode: atomic\n" + "\n".join(records) + "\n"
    )


@pytest.mark.parametrize(
    "location",
    ["01.1,2.1", "1.01,2.1", "1.1,02.1", "1.1,2.01", "+1.1,2.1"],
)
@pytest.mark.parametrize("statement_count", [1, 2])
def test_merge_profiles_compares_numeric_coordinates(
    tmp_path: Path, location: str, statement_count: int
) -> None:
    first = _profile(tmp_path / "first.out", "one.go:1.1,2.1 1 1")
    second = _profile(tmp_path / "second.out", f"one.go:{location} {statement_count} 0")
    output = tmp_path / "merged.out"

    with pytest.raises(ProfileError, match="duplicate coverage block"):
        merge_profiles((first, second), output)

    assert not output.exists()


@pytest.mark.parametrize(
    "location",
    ["1,2", "x.1,2.1", "-1.1,2.1", "1.-1,2.1", "1.1,-2.1", "1.1,2.-1"],
)
def test_merge_profiles_rejects_invalid_coordinates(
    tmp_path: Path, location: str
) -> None:
    profile = _profile(tmp_path / "first.out", f"one.go:{location} 1 1")
    with pytest.raises(ProfileError, match="coverage block location"):
        merge_profiles((profile,), tmp_path / "merged.out")


def test_merge_profiles_preserves_noncanonical_disjoint_locations(
    tmp_path: Path,
) -> None:
    records = (
        "C:/source directory/one.go:01.1,2.1 1 1",
        "C:/source directory/one.go:3.1,04.1 2 0",
    )
    profile = _profile(tmp_path / "first.out", *records)
    output = tmp_path / "merged.out"

    merge_profiles((profile,), output)

    assert output.read_text(encoding="utf-8") == (
        "mode: atomic\n" + "\n".join(records) + "\n"
    )


@pytest.mark.parametrize("field", range(6))
@pytest.mark.parametrize("value", [2**63, 10**30])
def test_merge_profiles_rejects_go_integer_overflow(
    tmp_path: Path, field: int, value: int
) -> None:
    fields = [1, 1, 2, 1, 1, 1]
    fields[field] = value
    record = (
        f"one.go:{fields[0]}.{fields[1]},{fields[2]}.{fields[3]} "
        f"{fields[4]} {fields[5]}"
    )
    profile = _profile(tmp_path / "first.out", record)
    output = tmp_path / "merged.out"
    output.write_text("previous verified output\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="Go int64 range"):
        merge_profiles((profile,), output)

    assert output.read_text(encoding="utf-8") == "previous verified output\n"


@pytest.mark.parametrize("field", range(6))
@pytest.mark.parametrize("value", [2**31, 2**63 - 1])
def test_merge_profiles_accepts_full_go_64_bit_integer_range(
    tmp_path: Path, field: int, value: int
) -> None:
    fields = [1, 1, 2, 1, 1, 1]
    fields[field] = value
    record = (
        f"one.go:{fields[0]}.{fields[1]},{fields[2]}.{fields[3]} "
        f"{fields[4]} {fields[5]}"
    )
    profile = _profile(tmp_path / "first.out", record)
    output = tmp_path / "merged.out"

    merge_profiles((profile,), output)

    assert output.read_text(encoding="utf-8") == f"mode: atomic\n{record}\n"
