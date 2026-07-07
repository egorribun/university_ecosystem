#!/usr/bin/env python3
"""Script to generate a structured seed corpus for the Atheris API fuzzer."""

from pathlib import Path


def main() -> None:
    corpus_dir = Path("tests/fuzz/corpus")
    corpus_dir.mkdir(parents=True, exist_ok=True)

    # Seed 1: Safe clean inputs
    # Format matches ConsumeUnicodeNoSurrogates, ConsumeBool, etc. calls in run_atheris.py
    seed_safe = (
        b"<html><body><h1>Hello World</h1><p>This is a safe paragraph.</p></body></html>\x01"  # HTML + allow_basic=True
        b"safe_document.pdf\x00\x00\x00\x0a"  # filename + max_length=10
        b"https://university.edu/dashboard\x01"  # url + dnd_enabled=True
        b"Europe/London\x01\x00\x00\x00\x1412:00\x01\x00\x00\x00\x1413:00"  # timezone + dnd_start_bool=True + dnd_start + dnd_end_bool=True + dnd_end
        b"valid-reset-token-12345"  # token
        b"SecurePassword123!"  # password
    )
    (corpus_dir / "seed_safe.bin").write_bytes(seed_safe)

    # Seed 2: XSS and Path Traversal attempts
    seed_xss_traversal = (
        b"<script>alert('XSS')</script><img src=x onerror=alert(1)>\x00"  # HTML + allow_basic=False
        b"../../../../etc/passwd\x00\x00\x01\x00"  # filename + max_length=256
        b"javascript:alert('XSS')\x00"  # url + dnd_enabled=False
        b"Asia/Tokyo\x00\x00"  # timezone + dnd_start_bool=False + dnd_end_bool=False
        b"malicious-token-'; DROP TABLE users; --"  # token
        b"Weak"  # password
    )
    (corpus_dir / "seed_xss_traversal.bin").write_bytes(seed_xss_traversal)

    # Seed 3: SQL Injection and weird boundary inputs
    seed_sql_bounds = (
        b"Normal text but with a single quote ' OR 1=1 --\x01"
        b"NUL\x00.txt\x00\x00\x00\x05"
        b"data:text/html,<script>alert(1)</script>\x01"
        b"Invalid/Timezone\x01\x00\x00\x00\x02XX\x01\x00\x00\x00\x02YY"
        b"admin'--"
        b"x" * 500
    )
    (corpus_dir / "seed_sql_bounds.bin").write_bytes(seed_sql_bounds)

    print(f"Generated seed files in {corpus_dir.absolute()}")


if __name__ == "__main__":
    main()
