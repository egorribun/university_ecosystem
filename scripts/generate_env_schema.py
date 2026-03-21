#!/usr/bin/env python3
"""MOD-W9-04: Auto-generate .env.schema.json from Pydantic Settings model.

Run:
    uv run python scripts/generate_env_schema.py

CI gate (add to required-checks.yml):
    python scripts/generate_env_schema.py && git diff --exit-code .env.schema.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path so 'app' is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    # Set minimum required env vars so Settings can be imported without a .env
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    os.environ.setdefault("SECRET_KEY", "x" * 32)
    os.environ.setdefault("ELASTICSEARCH_PASSWORD", "x")

    from app.core.config import Settings

    schema = Settings.model_json_schema()
    out_path = ROOT / ".env.schema.json"
    out_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Stats
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    optional_count = sum(1 for k in props if k not in required)
    required_count = len(required)

    print(f"✓ Wrote {out_path}")
    print(f"  Required fields : {required_count}")
    print(f"  Optional fields : {optional_count}")
    print(f"  Total           : {len(props)}")


if __name__ == "__main__":
    main()
