import os
import re

mapping = {
    "tests/test_auth_wave5_coverage.py": "tests/test_auth_coverage_extra.py",
    "tests/test_wave6_coverage.py": "tests/test_storage.py",
    "tests/test_wave7_coverage.py": "tests/test_events.py",
    "tests/test_wave8_coverage.py": "tests/test_services_extra.py",
    "tests/test_wave9_coverage.py": "tests/test_graphql.py",
    "tests/test_wave10_coverage.py": "tests/test_units.py",
    "tests/test_coverage_boost_v2.py": "tests/test_api_deps.py",
    "tests/test_coverage_boost_v3.py": "tests/test_units.py",
    "tests/test_coverage_boost_v4.py": "tests/test_units.py",
    "tests/test_z_coverage_monster.py": "tests/test_units.py",
}

for src, dst in mapping.items():
    if not os.path.exists(src):
        print(f"Not found: {src}")
        continue

    with open(src, encoding="utf-8") as f:
        content = f.read()

    # Remove future imports to avoid SyntaxError when appended
    content = re.sub(r"from __future__ import annotations", "", content)

    header = f"\n\n# ==========================================\n# Appended from {os.path.basename(src)}\n# ==========================================\n"

    with open(dst, "a", encoding="utf-8") as f:
        f.write(header + content)

    os.remove(src)
    print(f"Appended {src} -> {dst}")
