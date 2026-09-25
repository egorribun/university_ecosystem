"""Keep depcheck's direct axe asset exception tied to real accessibility scans."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_direct_axe_asset_remains_a_reviewed_depcheck_dependency() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    depcheck = (FRONTEND / "scripts/lint-depcheck.mjs").read_text(encoding="utf-8")
    asset_users = (
        FRONTEND / "tests/e2e/accessibility.spec.ts",
        FRONTEND / "tests/e2e/a11y-public.spec.ts",
        FRONTEND / "scripts/authenticated-visual-audit.mjs",
    )

    assert package["devDependencies"]["axe-core"]
    assert all(
        "node_modules/axe-core/axe.min.js" in path.read_text(encoding="utf-8")
        for path in asset_users
    )
    assert '"axe-core",' in depcheck
