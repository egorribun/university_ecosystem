#!/usr/bin/env python3
"""Build a deterministic static Inter 400 TTF from the locked Fontsource subsets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import brotli
from fontTools import __version__ as FONTTOOLS_VERSION
from fontTools.merge import Merger
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONTTOOLS_REQUIRED = "4.66.1"
BROTLI_REQUIRED = "1.2.0"
CSS_SHA256 = "78d97e4cbc385b8d0f86f21f650073c149eda98423bbdc49b13a13836d81e571"
INPUTS = {
    "inter-latin-wght-normal.woff2": "3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62",
    "inter-latin-ext-wght-normal.woff2": "34b9c504cab7a73e37b746343a449132e56cf7b5481af2cb81dc74dcff25c956",
    "inter-vietnamese-wght-normal.woff2": "5c66f9e07e90c6d4ac4922cc68d60de26c17b1858e677fb5e603fce3952b3ff2",
    "inter-cyrillic-wght-normal.woff2": "71d5ee93cc1e9f1d520a3a8b66456de18c7879d8df09d57fcd2eaff75fef0075",
    "inter-cyrillic-ext-wght-normal.woff2": "ca157063339ac4ad418f214f3abfed119b0798ab4d377386ce5c9e5a7a435ebd",
}
LOCKED_INTER_VERSION = "5.3.0"
LOCKED_INTER_INTEGRITY = "sha512-OupL48va4JNofb97w6NYeF9S7W/kHNKM0Er8Dem5nqi4jeOLrVJDoE8tZEpnMJmtkvNbB1EIPPwHcdkF6b1oUA=="
SUBSET_NAME_PARTS = ("latin", "vietnamese", "cyrillic")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_locked_inter(frontend_root: Path) -> None:
    lock_path = frontend_root / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    package = lock.get("packages", {}).get("node_modules/@fontsource-variable/inter")
    if not isinstance(package, dict):
        raise RuntimeError("Locked @fontsource-variable/inter package entry is missing")
    if package.get("version") != LOCKED_INTER_VERSION:
        raise RuntimeError(
            "Inter package version does not match the source-hash manifest"
        )
    if package.get("integrity") != LOCKED_INTER_INTEGRITY:
        raise RuntimeError(
            "Inter package integrity does not match the source-hash manifest"
        )
    if package.get("license") != "OFL-1.1":
        raise RuntimeError("Inter package license is not OFL-1.1")


def require_subset_sources(source_dir: Path) -> list[Path]:
    css_path = source_dir.parent / "wght.css"
    if sha256(css_path) != CSS_SHA256:
        raise RuntimeError("Inter weight stylesheet SHA-256 mismatch")
    css = css_path.read_text(encoding="utf-8")
    css_sources = set(re.findall(r"url\(\./files/([^\)]+)\)", css))
    expected_sources = {
        filename
        for filename in css_sources
        if any(part in filename for part in SUBSET_NAME_PARTS)
    }
    if expected_sources != set(INPUTS):
        raise RuntimeError(
            "Inter Latin/Cyrillic source subsets changed: "
            f"expected {sorted(INPUTS)}, found {sorted(expected_sources)}"
        )

    paths = []
    for filename, expected_hash in INPUTS.items():
        path = source_dir / filename
        if not path.is_file():
            raise RuntimeError(f"Required locked Inter subset is missing: {filename}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise RuntimeError(f"Inter subset SHA-256 mismatch: {filename}")
        paths.append(path)
    return paths


def unicode_map(font: TTFont) -> dict[int, str]:
    best = font.getBestCmap()
    if best is None:
        raise RuntimeError("Input font has no Unicode cmap")
    return best


def generate(
    source_dir: Path, output_path: Path, frontend_root: Path
) -> dict[str, object]:
    if FONTTOOLS_VERSION != FONTTOOLS_REQUIRED:
        raise RuntimeError(
            f"fontTools {FONTTOOLS_REQUIRED} is required; found {FONTTOOLS_VERSION}"
        )
    if getattr(brotli, "__version__", None) != BROTLI_REQUIRED:
        raise RuntimeError(f"Brotli {BROTLI_REQUIRED} is required")
    require_locked_inter(frontend_root)
    input_paths = require_subset_sources(source_dir)
    expected_cmap: dict[int, str] = {}
    source_units_per_em: int | None = None

    with tempfile.TemporaryDirectory(prefix="activity-inter-static-") as temp_name:
        temp_dir = Path(temp_name)
        static_paths: list[str] = []
        for index, input_path in enumerate(input_paths):
            variable = TTFont(input_path, recalcBBoxes=False, recalcTimestamp=False)
            if "fvar" not in variable:
                raise RuntimeError(
                    f"Inter subset is no longer variable: {input_path.name}"
                )
            axes = {axis.axisTag for axis in variable["fvar"].axes}
            if axes != {"wght"}:
                raise RuntimeError(
                    f"Unexpected variable axes in {input_path.name}: {axes}"
                )
            if source_units_per_em is None:
                source_units_per_em = variable["head"].unitsPerEm
            elif variable["head"].unitsPerEm != source_units_per_em:
                raise RuntimeError("Inter subsets disagree on unitsPerEm")
            expected_cmap.update(unicode_map(variable))
            static = instantiateVariableFont(variable, {"wght": 400}, inplace=False)
            static.flavor = None
            static_path = temp_dir / f"subset-{index}.ttf"
            static.save(static_path)
            static_paths.append(str(static_path))

        merged = Merger().merge(static_paths)
        merged_cmap = unicode_map(merged)
        if set(merged_cmap) != set(expected_cmap):
            missing = sorted(set(expected_cmap) - set(merged_cmap))
            extra = sorted(set(merged_cmap) - set(expected_cmap))
            raise RuntimeError(
                f"Merged Inter cmap changed (missing={missing[:8]}, extra={extra[:8]})"
            )

        # A fixed OpenType timestamp makes reruns byte-for-byte reproducible.
        stable_timestamp = int(
            (
                datetime(2025, 1, 1, tzinfo=UTC) - datetime(1904, 1, 1, tzinfo=UTC)
            ).total_seconds()
        )
        merged["head"].created = stable_timestamp
        merged["head"].modified = stable_timestamp
        merged["head"].checkSumAdjustment = 0
        merged.flavor = None
        merged.recalcTimestamp = False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged.save(output_path)

    result = TTFont(output_path, recalcBBoxes=False, recalcTimestamp=False)
    if any(
        table in result for table in ("fvar", "gvar", "HVAR", "MVAR", "avar", "STAT")
    ):
        raise RuntimeError("Generated PDF font still contains variable-font tables")
    output_cmap = unicode_map(result)
    if set(output_cmap) != set(expected_cmap):
        raise RuntimeError(
            "Generated static font does not preserve every source subset codepoint"
        )
    if result["head"].unitsPerEm != source_units_per_em:
        raise RuntimeError("Generated font changed unitsPerEm")
    if "glyf" not in result or "hmtx" not in result or "name" not in result:
        raise RuntimeError("Generated font is missing jsPDF TrueType tables")

    return {
        "fonttools_version": FONTTOOLS_VERSION,
        "weight": 400,
        "source_subset_sha256": INPUTS,
        "unicode_codepoints": len(output_cmap),
        "glyphs": result["maxp"].numGlyphs,
        "output_sha256": sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "output": output_path.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--font-source-dir",
        type=Path,
        help="Fontsource package files directory (defaults to this frontend's locked node_modules)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output TTF path (defaults to src/assets/fonts/inter-latin-cyrillic-400.ttf)",
    )
    args = parser.parse_args()
    frontend_root = Path(__file__).resolve().parents[1]
    source_dir = args.font_source_dir or (
        frontend_root / "node_modules" / "@fontsource-variable" / "inter" / "files"
    )
    output_path = args.output or (
        frontend_root / "src" / "assets" / "fonts" / "inter-latin-cyrillic-400.ttf"
    )
    result = generate(source_dir.resolve(), output_path.resolve(), frontend_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
