from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a complete source and test inventory manifest."
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=REPOSITORY_ROOT / "quality" / "ownership-mapping.json",
        help="Path to ownership mapping configuration JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "quality" / "inventory.json",
        help="Output destination path for the generated inventory JSON",
    )
    return parser.parse_args(argv)


def resolve_owner(relative_path: str, teams: dict[str, str]) -> str | None:
    # Longest prefix match
    best_match_prefix = ""
    best_owner = None

    posix_path = relative_path.replace("\\", "/")
    for prefix, owner in teams.items():
        prefix_clean = prefix.rstrip("/")
        if posix_path == prefix_clean or posix_path.startswith(prefix_clean + "/"):
            if len(prefix_clean) > len(best_match_prefix):
                best_match_prefix = prefix_clean
                best_owner = owner

    return best_owner


def is_tier0(relative_path: str, tier0_rules: list[str]) -> bool:
    posix_path = relative_path.replace("\\", "/")
    for pattern in tier0_rules:
        if fnmatch.fnmatchcase(posix_path, pattern) or fnmatch.fnmatchcase(
            Path(posix_path).name, pattern
        ):
            return True
    return False


def is_generated(relative_path: str, generated_patterns: list[str]) -> bool:
    posix_path = relative_path.replace("\\", "/")
    for pattern in generated_patterns:
        if fnmatch.fnmatchcase(posix_path, pattern) or fnmatch.fnmatchcase(
            Path(posix_path).name, pattern
        ):
            return True
    return False


def classify_file(relative_path: str, generated_patterns: list[str]) -> str:
    posix_path = relative_path.replace("\\", "/")
    if is_generated(posix_path, generated_patterns):
        return "generated"

    # Test classifications
    if posix_path.endswith((".test.ts", ".test.tsx", "_test.go")):
        return "test"
    if (
        posix_path.startswith("tests/")
        and Path(posix_path).name.startswith("test_")
        and posix_path.endswith(".py")
    ):
        return "test"

    # Source classifications
    source_dirs = {"app", "frontend/src", "services", "native", "crates"}
    for s_dir in source_dirs:
        if posix_path.startswith(s_dir + "/"):
            # Ensure it is a source code file extension
            if posix_path.endswith((".py", ".ts", ".tsx", ".go", ".rs")):
                return "source"

    # Infrastructure/utility
    return "utility"


def scan_repository(mapping_config: dict[str, object]) -> list[dict[str, object]]:
    teams = mapping_config.get("teams", {})
    tier0_rules = mapping_config.get("tier0_rules", [])
    generated_patterns = mapping_config.get("generated_patterns", [])

    records = []

    # Traverse directory tree
    for path in REPOSITORY_ROOT.rglob("*"):
        if not path.is_file():
            continue

        relative_path = str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")

        # Fast ignore check for major dependency/git folders
        parts = relative_path.split("/")
        if any(
            part
            in {
                ".git",
                ".venv",
                "node_modules",
                "dist",
                "build",
                "__pycache__",
                ".pytest_cache",
                ".tmp",
            }
            for part in parts
        ):
            continue

        file_class = classify_file(relative_path, generated_patterns)

        owner = resolve_owner(relative_path, teams)
        tier0_status = is_tier0(relative_path, tier0_rules)

        records.append(
            {
                "path": relative_path,
                "classification": file_class,
                "owner": owner,
                "tier0": tier0_status and file_class == "source",
            }
        )

    records.sort(key=lambda r: str(r["path"]))
    return records


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_arguments(argv)

    if not args.mapping.exists():
        print(
            f"ERROR: ownership mapping file not found at {args.mapping}",
            file=sys.stderr,
        )
        return 1

    try:
        mapping_config = json.loads(args.mapping.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"ERROR: failed to load mapping configuration: {error}", file=sys.stderr)
        return 1

    records = scan_repository(mapping_config)

    manifest = {"version": 1, "files": records}

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Inventory successfully generated at {args.output}")
        return 0
    except Exception as error:
        print(f"ERROR: failed to write inventory: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
