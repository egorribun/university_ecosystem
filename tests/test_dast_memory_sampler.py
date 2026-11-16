"""Parsing and summary contracts for the DAST runner memory sampler (AUD-381)."""

from __future__ import annotations

import asyncio
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


def _owned_context() -> tuple[dict[str, str], dict[str, object]]:
    env = {
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "2",
    }
    return env, {
        "schema_version": 1,
        "identity": {
            "source_sha": env["GITHUB_SHA"],
            "run_id": env["GITHUB_RUN_ID"],
            "run_attempt": env["GITHUB_RUN_ATTEMPT"],
            "image": "ghcr.io/zaproxy/zaproxy@sha256:" + "b" * 64,
            "rules_sha256": "c" * 64,
            "hook_sha256": "d" * 64,
        },
        "run_nonce": "e" * 32,
        "started_ns": 123,
    }


def test_context_identity_and_nonce_must_match_current_run() -> None:
    from scripts.quality import dast_memory_sampler as sampler

    env, context = _owned_context()
    assert sampler._context_nonce(json.dumps(context).encode(), env) == "e" * 32
    context["run_nonce"] = "e" * 31 + ";"
    assert sampler._context_nonce(json.dumps(context).encode(), env) is None
    context["run_nonce"] = "e" * 32
    env["GITHUB_RUN_ATTEMPT"] = "3"
    assert sampler._context_nonce(json.dumps(context).encode(), env) is None
    env["GITHUB_RUN_ATTEMPT"] = "2"
    identity = context["identity"]
    assert isinstance(identity, dict)
    identity["source_sha"] = "invalid"
    assert sampler._context_nonce(json.dumps(context).encode(), env) is None


def _cgroup_fixture(root: Path) -> tuple[Path, Path, str]:
    proc = root / "proc"
    cgroups = root / "cgroup"
    container_id = "f" * 64
    process = proc / "234"
    process.mkdir(parents=True)
    (process / "stat").write_text(
        "234 (scanner) S " + "0 " * 18 + "98765 0\n", encoding="utf-8"
    )
    (process / "cgroup").write_text(
        f"0::/system.slice/docker-{container_id}.scope\n", encoding="utf-8"
    )
    group = cgroups / "system.slice" / f"docker-{container_id}.scope"
    group.mkdir(parents=True)
    (group / "cgroup.procs").write_text("234\n", encoding="utf-8")
    (group / "memory.current").write_text("1024\n", encoding="utf-8")
    (group / "memory.peak").write_text("2048\n", encoding="utf-8")
    (group / "memory.max").write_text("4096\n", encoding="utf-8")
    (group / "memory.events").write_text("oom 2\noom_kill 1\n", encoding="utf-8")
    return proc, cgroups, container_id


def test_container_metrics_require_exact_pid_and_cgroup_binding(tmp_path: Path) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    proc, cgroups, container_id = _cgroup_fixture(tmp_path)
    assert sampler._container_cgroup_sample(proc, cgroups, 234, container_id) == {
        "status": "sampled",
        "current_bytes": 1024,
        "peak_bytes": 2048,
        "limit_bytes": 4096,
        "limit_state": "value",
        "oom_events": 2,
        "oom_kill_events": 1,
    }
    assert sampler._container_cgroup_sample(proc, cgroups, 234, "a" * 64) == {
        "status": "unavailable"
    }
    (
        cgroups / "system.slice" / f"docker-{container_id}.scope" / "cgroup.procs"
    ).write_text("235\n", encoding="utf-8")
    assert sampler._container_cgroup_sample(proc, cgroups, 234, container_id) == {
        "status": "unavailable"
    }


def test_container_summary_is_explicitly_sampled_and_sanitized() -> None:
    from scripts.quality import dast_memory_sampler as sampler

    records = [
        {"container_memory": {"status": "unavailable"}},
        {
            "container_memory": {
                "status": "sampled",
                "current_bytes": 1024,
                "peak_bytes": 2048,
                "limit_bytes": None,
                "limit_state": "unlimited",
                "oom_events": 1,
                "oom_kill_events": 0,
            }
        },
    ]
    text = sampler.summarize_records(records)
    assert "Container cgroup: 1 sampled observation" in text
    assert "maximum observed current: 1024 bytes" in text
    assert "maximum observed peak: 2048 bytes" in text
    assert "maximum observed oom_kill: 0" in text
    assert "does not cover events after the last observation" in text


@pytest.mark.parametrize(
    "payload",
    [
        b"{}",
        b"not JSON",
        b'{"schema_version":1,"schema_version":1}',
        b"[]",
        b"\xff",
    ],
)
def test_context_rejects_malformed_or_duplicate_input(payload: bytes) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    env, _ = _owned_context()
    assert sampler._context_nonce(payload, env) is None


@pytest.mark.parametrize("field", ["schema_version", "started_ns", "identity"])
def test_context_rejects_wrong_types(field: str) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    env, context = _owned_context()
    context[field] = True
    assert sampler._context_nonce(json.dumps(context).encode(), env) is None


def test_context_file_guard_rejects_relative_path() -> None:
    from scripts.quality import dast_memory_sampler as sampler

    assert sampler._read_private_context(Path("relative")) is None


def test_private_context_uses_owned_files_without_following_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from typing import cast

    from scripts.quality import dast_memory_sampler as sampler

    _, context = _owned_context()
    payload = json.dumps(context).encode()
    opened: list[tuple[object, int, int | None]] = []
    closed: list[int] = []
    work = SimpleNamespace(st_uid=42, st_mode=0o40700)
    file_info = SimpleNamespace(
        st_uid=42, st_mode=0o100600, st_nlink=1, st_size=len(payload)
    )

    def fake_open(path: object, flags: int, *, dir_fd: int | None = None) -> int:
        opened.append((path, flags, dir_fd))
        return len(opened)

    fake_os = SimpleNamespace(
        name="posix",
        O_RDONLY=1,
        O_DIRECTORY=2,
        O_NOFOLLOW=4,
        O_NONBLOCK=8,
        open=fake_open,
        close=closed.append,
        fstat=lambda fd: work if fd == 2 else file_info,
        getuid=lambda: 42,
        read=lambda _fd, _size: payload,
    )
    monkeypatch.setattr(sampler, "os", fake_os)
    assert sampler._read_private_context(tmp_path) == payload
    assert [(path, flags, parent) for path, flags, parent in opened] == [
        (tmp_path, 7, None),
        ("zap-private", 7, 1),
        ("context.json", 13, 2),
    ]
    assert closed == [3, 2, 1]
    opened.clear()
    closed.clear()
    file_info.st_mode = 0o100644
    assert sampler._read_private_context(tmp_path) is None
    assert closed == [3, 2, 1]
    opened.clear()
    closed.clear()
    file_info.st_mode = 0o100600
    work.st_uid = 43
    assert sampler._read_private_context(tmp_path) is None
    assert closed == [2, 1]
    work.st_uid = 42
    for attribute, value in (
        ("st_uid", 43),
        ("st_nlink", 2),
        ("st_size", 0),
        ("st_size", sampler._MAX_CONTEXT_BYTES + 1),
        ("st_mode", 0o120777),
    ):
        opened.clear()
        old = getattr(file_info, attribute)
        setattr(file_info, attribute, value)
        assert sampler._read_private_context(tmp_path) is None
        setattr(file_info, attribute, old)

    opened.clear()
    fake_os.read = lambda _fd, size: b"x" * size
    assert sampler._read_private_context(tmp_path) is None

    def fail_open(*_args: object, **_kwargs: object) -> int:
        raise OSError("private details")

    fake_os.open = fail_open
    assert sampler._read_private_context(tmp_path) is None

    class SymlinkedTemp:
        parts = ("/", "temporary")

        def is_absolute(self) -> bool:
            return True

        def resolve(self, *, strict: bool) -> Path:
            assert strict
            return tmp_path

    assert sampler._read_private_context(cast(Path, SymlinkedTemp())) is None


def test_cgroup_missing_fields_are_unavailable_and_max_is_unlimited(
    tmp_path: Path,
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    proc, cgroups, container_id = _cgroup_fixture(tmp_path)
    group = cgroups / "system.slice" / f"docker-{container_id}.scope"
    (group / "memory.max").write_text("max\n", encoding="utf-8")
    (group / "memory.peak").unlink()
    (group / "memory.events").write_text(
        "low 1\ninvalid\noom 5\noom 6\noom_kill not-a-number\n", encoding="utf-8"
    )
    result = sampler._container_cgroup_sample(proc, cgroups, 234, container_id)
    assert result["status"] == "sampled"
    assert result["limit_state"] == "unlimited"
    assert result["limit_bytes"] is None
    assert result["peak_bytes"] is None
    assert result["oom_events"] is None
    assert result["oom_kill_events"] is None


def test_cgroup_with_no_readable_counters_is_unavailable(tmp_path: Path) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    proc, cgroups, container_id = _cgroup_fixture(tmp_path)
    group = cgroups / "system.slice" / f"docker-{container_id}.scope"
    for name in ("memory.current", "memory.peak", "memory.max", "memory.events"):
        (group / name).unlink()
    assert sampler._container_cgroup_sample(proc, cgroups, 234, container_id) == {
        "status": "unavailable"
    }


def test_cgroup_v1_and_pid_reuse_cannot_be_attributed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    proc, cgroups, container_id = _cgroup_fixture(tmp_path)
    membership = proc / "234" / "cgroup"
    original = membership.read_bytes()
    membership.write_bytes(b"5:memory:/docker/example\n")
    assert sampler._container_cgroup_sample(proc, cgroups, 234, container_id) == {
        "status": "unsupported"
    }
    membership.write_bytes(original)
    real_read = sampler._read_bounded
    stat_reads = 0

    def changing_start(
        path: Path, limit: int = sampler._MAX_COUNTER_BYTES
    ) -> bytes | None:
        nonlocal stat_reads
        value = real_read(path, limit)
        if path.name == "stat":
            stat_reads += 1
            if stat_reads == 2 and value is not None:
                return value.replace(b"98765", b"98766")
        return value

    monkeypatch.setattr(sampler, "_read_bounded", changing_start)
    assert sampler._container_cgroup_sample(proc, cgroups, 234, container_id) == {
        "status": "unavailable"
    }


def test_cgroup_rejects_invalid_and_unreadable_membership(tmp_path: Path) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    proc, cgroups, container_id = _cgroup_fixture(tmp_path)
    membership = proc / "234" / "cgroup"
    for value in (
        b"0::/system.slice/../docker-" + container_id.encode() + b".scope\n",
        b"0::/one\n0::/two\n",
        b"0::/\xff\n",
        b"0::/does-not-exist/docker-" + container_id.encode() + b".scope\n",
    ):
        membership.write_bytes(value)
        assert sampler._container_cgroup_sample(proc, cgroups, 234, container_id) == {
            "status": "unavailable"
        }
    (proc / "234" / "stat").unlink()
    assert sampler._container_cgroup_sample(proc, cgroups, 234, container_id) == {
        "status": "unavailable"
    }


def test_cgroup_rejects_resolved_path_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    proc, cgroups, container_id = _cgroup_fixture(tmp_path)
    group = cgroups / "system.slice" / f"docker-{container_id}.scope"
    resolve = Path.resolve

    def different_group(path: Path, strict: bool = False) -> Path:
        return tmp_path / "changed" if path == group else resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", different_group)
    assert sampler._container_cgroup_sample(proc, cgroups, 234, container_id) == {
        "status": "unavailable"
    }


class _FakeStream:
    def __init__(self, payload: bytes, *, hangs: bool = False) -> None:
        self.payload = payload
        self.hangs = hangs

    async def read(self, length: int) -> bytes:
        if self.hangs:
            await asyncio.sleep(10)
        result, self.payload = self.payload[:length], self.payload[length:]
        return result


class _FakeProcess:
    def __init__(self, payload: bytes, *, hangs: bool = False) -> None:
        self.stdout = _FakeStream(payload, hangs=hangs)
        self.returncode: int | None = None
        self.killed = False

    async def wait(self) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.killed = True


def test_inspection_uses_fixed_local_only_command_and_does_not_publish_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    process = _FakeProcess(("f" * 64 + " 234 true\n").encode())
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def fake_exec(*args: object, **kwargs: object) -> _FakeProcess:
        calls.append((args, kwargs))
        return process

    monkeypatch.setattr(sampler.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(
        sampler._inspect_owned_container("/usr/bin/docker", "zap-" + "e" * 32)
    ) == (
        "f" * 64,
        234,
    )
    args, kwargs = calls[0]
    assert args == (
        "/usr/bin/docker",
        "--host",
        "unix:///var/run/docker.sock",
        "inspect",
        "--type",
        "container",
        "--format",
        "{{.Id}} {{.State.Pid}} {{.State.Running}}",
        "zap-" + "e" * 32,
    )
    assert kwargs["env"] == {"DOCKER_CONFIG": "/dev/null"}
    assert kwargs["stderr"] == asyncio.subprocess.DEVNULL


@pytest.mark.parametrize("payload,hangs", [(b"x" * 257, False), (b"", True)])
def test_inspection_bounds_output_and_timeout(
    monkeypatch: pytest.MonkeyPatch, payload: bytes, hangs: bool
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    process = _FakeProcess(payload, hangs=hangs)

    async def fake_exec(*_args: object, **_kwargs: object) -> _FakeProcess:
        return process

    monkeypatch.setattr(sampler.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(sampler, "DOCKER_TIMEOUT_SECONDS", 0.01)
    assert (
        asyncio.run(sampler._inspect_owned_container("docker", "zap-" + "e" * 32))
        is None
    )
    assert process.killed


@pytest.mark.parametrize("payload", [b"invalid\n", b"f" * 64 + b" 234 false\n"])
def test_inspection_rejects_nonrunning_or_malformed_result(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    process = _FakeProcess(payload)

    async def fake_exec(*_args: object, **_kwargs: object) -> _FakeProcess:
        return process

    monkeypatch.setattr(sampler.asyncio, "create_subprocess_exec", fake_exec)
    assert (
        asyncio.run(sampler._inspect_owned_container("docker", "zap-" + "e" * 32))
        is None
    )


def test_inspection_handles_missing_stdout_and_kill_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    class BrokenProcess:
        stdout = None
        returncode = None

        def kill(self) -> None:
            raise OSError("private details")

    async def fake_exec(*_args: object, **_kwargs: object) -> BrokenProcess:
        return BrokenProcess()

    monkeypatch.setattr(sampler.asyncio, "create_subprocess_exec", fake_exec)
    assert (
        asyncio.run(sampler._inspect_owned_container("docker", "zap-" + "e" * 32))
        is None
    )


def test_observer_locks_identity_and_does_not_expose_private_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    env, context = _owned_context()
    env["RUNNER_TEMP"] = "C:/unused"
    monkeypatch.setattr(
        sampler, "_read_private_context", lambda _path: json.dumps(context).encode()
    )
    monkeypatch.setattr(
        sampler.shutil, "which", lambda _name: str(Path.cwd() / "docker")
    )
    monkeypatch.setattr(Path, "is_socket", lambda _self: True)
    names: list[str] = []
    ids = iter(["f" * 64, "a" * 64])

    async def fake_inspect(_docker: str, name: str) -> tuple[str, int]:
        names.append(name)
        return next(ids), 234

    monkeypatch.setattr(sampler, "_inspect_owned_container", fake_inspect)
    monkeypatch.setattr(
        sampler,
        "_container_cgroup_sample",
        lambda *_args: {"status": "sampled", "current_bytes": 7},
    )
    observer = sampler._ContainerObserver(env)
    first = observer.observe()
    assert first == {"status": "sampled", "current_bytes": 7}
    assert names == ["zap-" + "e" * 32]
    assert "e" * 32 not in json.dumps(first)
    assert observer.observe() == {"status": "unavailable"}
    context["run_nonce"] = "a" * 32
    assert observer.observe() == {"status": "unavailable"}
    assert len(names) == 2


def test_observer_swallows_private_errors_and_inaccessible_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    env, context = _owned_context()
    env["RUNNER_TEMP"] = "C:/unused"
    observer = sampler._ContainerObserver(env)
    monkeypatch.setattr(
        sampler, "_read_private_context", lambda _path: json.dumps(context).encode()
    )
    monkeypatch.setattr(sampler.shutil, "which", lambda _name: None)
    assert observer.observe() == {"status": "unavailable"}

    monkeypatch.setattr(
        sampler.shutil, "which", lambda _name: str(Path.cwd() / "docker")
    )
    monkeypatch.setattr(Path, "is_socket", lambda _self: True)

    async def unavailable(_docker: str, _name: str) -> None:
        return None

    monkeypatch.setattr(sampler, "_inspect_owned_container", unavailable)
    assert observer.observe() == {"status": "unavailable"}

    def failed(_path: Path) -> None:
        raise RuntimeError("private details")

    monkeypatch.setattr(sampler, "_read_private_context", failed)
    assert observer.observe() == {"status": "unavailable"}


def test_container_observation_runs_every_third_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.quality import dast_memory_sampler as sampler

    stop = tmp_path / "stop"
    output = tmp_path / "telemetry.jsonl"
    calls: list[int] = []

    class FakeObserver:
        def __init__(self, _env: object) -> None:
            pass

        def observe(self) -> dict[str, object]:
            calls.append(1)
            return {"status": "unavailable"}

    sleeps = 0

    def stop_after_seven(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 7:
            stop.touch()

    monkeypatch.setattr(sampler, "_ContainerObserver", FakeObserver)
    monkeypatch.setattr(sampler, "take_sample", lambda: {"timestamp": "t"})
    monkeypatch.setattr(sampler.time, "sleep", stop_after_seven)
    assert sampler.sample(output, stop, 1, 60) == 0
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(calls) == 3
    assert ["container_memory" in record for record in records] == [
        True,
        False,
        False,
        True,
        False,
        False,
        True,
    ]
