"""Parsing and summary contracts for the DAST runner memory sampler (AUD-381)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality.dast_memory_sampler import (
    main,
    parse_meminfo,
    parse_oom_kill,
    parse_process_status,
    sample,
    summarize,
    summarize_records,
    top_processes,
)

MEMINFO = """MemTotal:       16384000 kB
MemFree:          100000 kB
MemAvailable:    8192000 kB
SwapTotal:       2048000 kB
SwapFree:        1024000 kB
"""

VMSTAT = """nr_free_pages 12345
oom_kill 3
pgfault 99
"""


def _status(name: str, rss_kb: int | None) -> str:
    rss = "" if rss_kb is None else f"VmRSS:\t{rss_kb:>8} kB\n"
    return f"Name:\t{name}\nState:\tS (sleeping)\n{rss}"


def test_parse_meminfo_reads_only_selected_keys_in_kb() -> None:
    assert parse_meminfo(MEMINFO) == {
        "MemTotal": 16384000,
        "MemAvailable": 8192000,
        "SwapFree": 1024000,
    }


def test_parse_meminfo_ignores_malformed_values() -> None:
    assert parse_meminfo("MemAvailable:\tunknown\nSwapFree:\n") == {}


def test_parse_process_status_extracts_name_and_vmrss() -> None:
    assert parse_process_status(_status("java", 2048)) == {
        "name": "java",
        "rss_kb": 2048,
    }


def test_parse_process_status_skips_kernel_threads_without_vmrss() -> None:
    assert parse_process_status(_status("kworker/0:1", None)) is None


def test_parse_oom_kill_reads_counter_and_tolerates_absence() -> None:
    assert parse_oom_kill(VMSTAT) == 3
    assert parse_oom_kill("pgfault 99\n") is None
    assert parse_oom_kill("oom_kill notanumber\n") is None


def test_top_processes_ranks_by_rss_and_limits_to_five(tmp_path: Path) -> None:
    sizes = {101: 100, 102: 900, 103: 500, 104: 700, 105: 300, 106: 800, 107: 50}
    for pid, rss in sizes.items():
        directory = tmp_path / str(pid)
        directory.mkdir()
        (directory / "status").write_text(_status(f"proc{pid}", rss), encoding="utf-8")
    (tmp_path / "self").mkdir()
    (tmp_path / "self" / "status").write_text(_status("ignored", 1), encoding="utf-8")
    (tmp_path / "201").mkdir()
    (tmp_path / "201" / "status").write_text(_status("kthread", None), encoding="utf-8")

    result = top_processes(tmp_path)

    assert [(item["pid"], item["rss_kb"]) for item in result] == [
        (102, 900),
        (106, 800),
        (104, 700),
        (103, 500),
        (105, 300),
    ]
    assert set(result[0]) == {"name", "rss_kb", "pid"}


def test_summarize_reports_minimum_available_peaks_and_oom_delta(
    tmp_path: Path,
) -> None:
    records = [
        {
            "timestamp": "2026-11-14T02:00:00+00:00",
            "mem_available_kb": 900,
            "oom_kill": 1,
            "top_processes": [
                {"name": "java", "pid": 10, "rss_kb": 400},
                {"name": "firefox", "pid": 11, "rss_kb": 100},
            ],
        },
        {
            "timestamp": "2026-11-14T02:00:05+00:00",
            "mem_available_kb": 300,
            "oom_kill": 4,
            "top_processes": [
                {"name": "java", "pid": 10, "rss_kb": 350},
                {"name": "firefox", "pid": 12, "rss_kb": 900},
            ],
        },
    ]
    path = tmp_path / "telemetry.jsonl"
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )

    text = summarize(path)

    assert "2 samples" in text
    assert "Minimum MemAvailable: 300 kB at 2026-11-14T02:00:05+00:00" in text
    assert "firefox: 900" in text
    assert "java: 400" in text
    assert text.index("firefox: 900") < text.index("java: 400")
    assert "oom_kill delta (last - first): 3" in text


def test_summarize_skips_error_records_and_reports_no_samples(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_text(
        json.dumps({"timestamp": "t", "error": "OSError"}) + "\n", encoding="utf-8"
    )

    text = summarize(path)

    assert "0 samples" in text
    assert "No usable samples" in text


def test_summarize_marks_missing_fields_unavailable() -> None:
    text = summarize_records(
        [{"timestamp": "t", "mem_available_kb": None, "oom_kill": None}]
    )

    assert "Minimum MemAvailable: unavailable" in text
    assert "oom_kill delta: unavailable" in text


def test_sample_writes_json_lines_until_stop_file_exists(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out" / "telemetry.jsonl"
    stop = tmp_path / "stop"
    stop.write_text("", encoding="utf-8")

    assert sample(output, stop, interval_seconds=0.01, max_seconds=5) == 0

    assert output.read_text(encoding="utf-8") == ""


def test_sample_records_timestamp_memory_and_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "telemetry.jsonl"
    stop = tmp_path / "stop"
    calls = {"count": 0}

    def fake_sleep(_seconds: float) -> None:
        calls["count"] += 1
        if calls["count"] >= 2:
            stop.write_text("", encoding="utf-8")

    monkeypatch.setattr("scripts.quality.dast_memory_sampler.time.sleep", fake_sleep)
    monkeypatch.setattr(
        "scripts.quality.dast_memory_sampler.take_sample",
        lambda: {
            "timestamp": "2026-11-14T02:00:00+00:00",
            "mem_available_kb": 1,
            "mem_total_kb": 2,
            "swap_free_kb": 3,
            "oom_kill": 0,
            "top_processes": [],
        },
    )

    assert sample(output, stop, interval_seconds=1, max_seconds=60) == 0

    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["mem_available_kb"] == 1


def test_sample_rejects_non_positive_intervals(tmp_path: Path) -> None:
    assert sample(tmp_path / "t.jsonl", tmp_path / "stop", 0, 10) == 2
    assert sample(tmp_path / "t.jsonl", tmp_path / "stop", 1, 0) == 2


def test_main_summarize_prints_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": "t",
                "mem_available_kb": 5,
                "oom_kill": 0,
                "top_processes": [{"name": "zap", "pid": 1, "rss_kb": 7}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert main(["summarize", str(path)]) == 0

    out = capsys.readouterr().out
    assert "zap: 7" in out
    assert "Minimum MemAvailable: 5 kB" in out


def test_summarize_preserves_complete_samples_after_interrupted_write(
    tmp_path: Path,
) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_text(
        json.dumps({"timestamp": "t", "mem_available_kb": 7, "oom_kill": 2})
        + '\n{"timestamp": "interrupted',
        encoding="utf-8",
    )

    text = summarize(path)

    assert "1 samples" in text
    assert "Minimum MemAvailable: 7 kB at t" in text
    assert "Ignored incomplete trailing sample." in text


@pytest.mark.parametrize("suffix", ['{"broken":\n', '{"broken":\n{}'])
def test_summarize_rejects_corrupt_complete_lines(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_text("{}\n" + suffix, encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        summarize(path)


def test_summarize_accepts_complete_final_record_without_newline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_text('{"timestamp": "t", "mem_available_kb": 7}', encoding="utf-8")

    text = summarize(path)

    assert "1 samples" in text
    assert "Ignored incomplete" not in text


def test_process_status_ignores_invalid_rss() -> None:
    assert parse_process_status("Name: java\nVmRSS: unknown\n") is None


def test_top_processes_tolerates_disappearing_process(tmp_path: Path) -> None:
    (tmp_path / "123").mkdir()
    assert top_processes(tmp_path) == []


@pytest.mark.parametrize("with_vmstat", [False, True])
def test_take_sample_reads_available_kernel_fields(
    tmp_path: Path,
    with_vmstat: bool,
) -> None:
    from scripts.quality.dast_memory_sampler import take_sample

    (tmp_path / "meminfo").write_text(MEMINFO, encoding="utf-8")
    if with_vmstat:
        (tmp_path / "vmstat").write_text(VMSTAT, encoding="utf-8")

    record = take_sample(tmp_path)

    assert record["mem_available_kb"] == 8192000
    assert record["mem_total_kb"] == 16384000
    assert record["swap_free_kb"] == 1024000
    assert record["oom_kill"] == (3 if with_vmstat else None)
    assert record["top_processes"] == []
    assert isinstance(record["timestamp"], str)


def test_sample_records_collection_error_without_private_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    stop = tmp_path / "stop"
    output = tmp_path / "telemetry.jsonl"

    def unavailable() -> dict[str, object]:
        raise OSError("private error detail")

    monkeypatch.setattr(sampler, "take_sample", unavailable)
    monkeypatch.setattr(sampler.time, "sleep", lambda _seconds: stop.touch())

    assert sample(output, stop, 1, 60) == 0
    record = json.loads(output.read_text(encoding="utf-8"))
    assert set(record) == {"timestamp", "error"}
    assert record["error"] == "OSError"
    assert "private" not in output.read_text(encoding="utf-8")


def test_summarize_ignores_blank_lines_and_non_object_records(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_text("\n  \n[]\n{}\n", encoding="utf-8")
    assert "1 samples" in summarize(path)


def test_main_sample_routes_arguments(tmp_path: Path) -> None:
    output = tmp_path / "telemetry.jsonl"
    stop = tmp_path / "stop"
    stop.touch()

    assert (
        main(
            [
                "sample",
                "--output",
                str(output),
                "--stop-file",
                str(stop),
                "--interval-seconds",
                "1",
                "--max-seconds",
                "60",
            ]
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == ""


def test_script_entrypoint_summarizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import runpy
    import sys

    from scripts.quality import dast_memory_sampler as sampler

    path = tmp_path / "telemetry.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [sampler.__file__, "summarize", str(path)])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(sampler.__file__, run_name="__main__")

    assert exit_info.value.code == 0
    assert "1 samples" in capsys.readouterr().out
