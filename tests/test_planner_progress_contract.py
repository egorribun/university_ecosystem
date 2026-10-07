from __future__ import annotations

import contextlib
import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import plan_mutmut_shards as planner


class _FlushRecordingStream(StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


class _FakeMetadata:
    def __init__(self, *, path: str) -> None:
        self.path = path
        self.exit_code_by_key: dict[str, int] = {}

    def load(self) -> None:
        self.exit_code_by_key = {
            "app.sample.x_calculate__mutmut_1": 0,
            "app.sample.x_calculate__mutmut_2": 0,
        }


class PlannerProgressContractTests(unittest.TestCase):
    def test_progress_payload_is_closed_safe_and_flushed(self) -> None:
        stream = _FlushRecordingStream()
        with contextlib.redirect_stderr(stream):
            planner._emit_progress("mutant_generation", "started")
            planner._emit_progress(
                "mutant_generation",
                "completed",
                elapsed_ms=17,
                counters={"mutant_count": 2},
            )

        records = [
            json.loads(line.removeprefix(planner._PROGRESS_PREFIX))
            for line in stream.getvalue().splitlines()
        ]
        self.assertEqual(stream.flush_count, 2)
        self.assertEqual(
            records,
            [
                {
                    "schema": "mutmut-planner-progress-v1",
                    "stage": "mutant_generation",
                    "event": "started",
                    "elapsed_ms": None,
                    "counters": {},
                },
                {
                    "schema": "mutmut-planner-progress-v1",
                    "stage": "mutant_generation",
                    "event": "completed",
                    "elapsed_ms": 17,
                    "counters": {"mutant_count": 2},
                },
            ],
        )
        self.assertNotIn("app.sample", stream.getvalue())

    def test_progress_rejects_unknown_labels_and_non_integer_counts(self) -> None:
        for stage, event, elapsed_ms, counters in (
            ("private/path", "started", None, None),
            ("planning", "private error", None, None),
            ("planning", "completed", True, None),
            ("planning", "completed", 1, {"mutant_name": 1}),
            ("planning", "completed", 1, {"mutant_count": True}),
        ):
            with self.subTest(stage=stage, event=event, counters=counters):
                with self.assertRaises(ValueError):
                    planner._emit_progress(
                        stage,
                        event,
                        elapsed_ms=elapsed_ms,
                        counters=counters,
                    )

    def test_interrupted_generation_has_only_a_flushed_start_marker(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="planner-progress-interrupted-"
        ) as temp:
            stream = _FlushRecordingStream()

            def fail_generation(_max_children: int) -> SimpleNamespace:
                last_record = json.loads(
                    stream.getvalue()
                    .splitlines()[-1]
                    .removeprefix(planner._PROGRESS_PREFIX)
                )
                self.assertEqual(last_record["stage"], "mutant_generation")
                self.assertEqual(last_record["event"], "started")
                self.assertGreater(stream.flush_count, 0)
                raise RuntimeError("do-not-emit-this")

            fake_cli = SimpleNamespace(
                copy_src_dir=lambda: None,
                copy_also_copy_files=lambda: None,
                setup_source_paths=lambda: None,
                create_mutants=fail_generation,
            )
            old_cwd = Path.cwd()
            try:
                os.chdir(temp)
                with (
                    patch.object(
                        planner,
                        "get_mutmut_config",
                        return_value=SimpleNamespace(mutate_only_covered_lines=False),
                    ),
                    patch.object(planner, "prepare_mutants_directory"),
                    contextlib.redirect_stderr(stream),
                ):
                    with self.assertRaisesRegex(RuntimeError, "do-not-emit-this"):
                        planner._generate_mutant_universe(fake_cli, max_children=8)
            finally:
                os.chdir(old_cwd)

            events = [
                json.loads(line.removeprefix(planner._PROGRESS_PREFIX))
                for line in stream.getvalue().splitlines()
            ]
            self.assertEqual(
                [(event["stage"], event["event"]) for event in events],
                [
                    ("generation_setup", "started"),
                    ("generation_setup", "completed"),
                    ("mutant_generation", "started"),
                ],
            )
            self.assertNotIn("do-not-emit-this", stream.getvalue())

    def test_main_progress_keeps_exact_mutant_population(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planner-progress-") as temp:
            root = Path(temp)
            changed_file_manifest = root / "changed.txt"
            changed_file_manifest.write_text("app/sample.py\n", encoding="utf-8")
            output_directory = root / "plan"
            stdout = StringIO()
            stderr = _FlushRecordingStream()

            def create_mutants(_max_children: int) -> SimpleNamespace:
                metadata_path = Path("mutants/app/sample.py.meta")
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.write_text("private mutant metadata", encoding="utf-8")
                Path("mutants/mutmut-stats.json").write_text(
                    json.dumps(
                        {
                            "tests_by_mangled_function_name": {
                                "app.sample.x_calculate": [
                                    "tests/test_sample.py::test_calculate"
                                ]
                            },
                            "duration_by_test": {
                                "tests/test_sample.py::test_calculate": 1.0
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return SimpleNamespace(mutated=1, ignored=0, unmodified=0)

            fake_cli = SimpleNamespace(
                copy_src_dir=lambda: None,
                copy_also_copy_files=lambda: None,
                setup_source_paths=lambda: None,
                create_mutants=create_mutants,
                walk_source_files=lambda: ["app/sample.py"],
                SourceFileMutationData=_FakeMetadata,
            )
            fake_manifest = {
                "source_files": {"app/sample.py": "digest"},
                "generated_files": {"app/sample.py": "digest"},
                "metadata_files": {"app/sample.py.meta": "digest"},
                "mutant_count": 2,
            }
            arguments = [
                "plan_mutmut_shards.py",
                "--changed-files",
                str(changed_file_manifest),
                "--num-shards",
                "2",
                "--max-children",
                "2",
                "--control-cycle-reserve-seconds",
                "1",
                "--metadata-startup-reserve-seconds",
                "1",
                "--max-timeout-seconds",
                "2100",
                "--output-directory",
                str(output_directory),
            ]

            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with (
                    patch.object(planner.sys, "argv", arguments),
                    patch.object(planner, "_load_mutmut_cli", return_value=fake_cli),
                    patch.object(
                        planner,
                        "get_mutmut_config",
                        return_value=SimpleNamespace(mutate_only_covered_lines=False),
                    ),
                    patch.object(planner, "prepare_mutants_directory"),
                    patch.object(
                        planner, "write_universe_manifest", return_value=fake_manifest
                    ),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    planner.main()
            finally:
                os.chdir(old_cwd)

            manifest = json.loads(
                (output_directory / "plan-manifest.json").read_text(encoding="utf-8")
            )
            observed = [
                name
                for shard_id in range(1, manifest["num_shards"] + 1)
                for name in (output_directory / f"shard-{shard_id:02d}.txt")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                observed,
                [
                    "app.sample.x_calculate__mutmut_1",
                    "app.sample.x_calculate__mutmut_2",
                ],
            )
            self.assertEqual(manifest["universe_count"], 2)
            self.assertEqual(len(observed), len(set(observed)))

            events = [
                json.loads(line.removeprefix(planner._PROGRESS_PREFIX))
                for line in stderr.getvalue().splitlines()
            ]
            self.assertEqual(stderr.flush_count, len(events))
            stage_events = [(event["stage"], event["event"]) for event in events]
            self.assertEqual(
                stage_events,
                [
                    ("generation_setup", "started"),
                    ("generation_setup", "completed"),
                    ("mutant_generation", "started"),
                    ("mutant_generation", "completed"),
                    ("metadata_scan", "started"),
                    ("metadata_scan", "completed"),
                    ("universe_manifest", "started"),
                    ("universe_manifest", "completed"),
                    ("changed_mutant_scan", "started"),
                    ("changed_mutant_scan", "completed"),
                    ("stats_load", "started"),
                    ("stats_load", "completed"),
                    ("planning", "started"),
                    ("planning", "completed"),
                    ("plan_publish", "started"),
                    ("plan_publish", "completed"),
                ],
            )
            for forbidden in (
                "app.sample.py",
                "app.sample.x_calculate",
                "tests/test_sample.py",
                "private mutant metadata",
            ):
                self.assertNotIn(forbidden, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
