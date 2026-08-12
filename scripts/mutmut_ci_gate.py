#!/usr/bin/env python3
"""Mutation testing gate script for CI.

Wraps the check_mutation_score.py utility to enforce a strict 100% viable
mutation score.
"""

from __future__ import annotations

import os
import sys

# Ensure current directory is in search path to import sibling modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from check_mutation_score import main
except ImportError as e:
    print(f"Error: Failed to import check_mutation_score: {e}", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    main(["--min-score", "100"])
