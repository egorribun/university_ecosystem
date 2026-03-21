import sys
import tomllib

# TD-NEW-005: Budget for mypy overrides.
# We currently have 9 [[tool.mypy.overrides]] blocks that disable strict typing
# or unused ignore checks. This budget should be decreased over time as the
# codebase becomes fully strictly typed.
OVERRIDE_BUDGET = 9

with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)

overrides = data.get("tool", {}).get("mypy", {}).get("overrides", [])
count = sum(
    1
    for o in overrides
    if o.get("disallow_untyped_defs") is False or o.get("warn_unused_ignores") is False
)

if count > OVERRIDE_BUDGET:
    print(f"::error::Mypy overrides budget exceeded: {count} > {OVERRIDE_BUDGET}")
    sys.exit(1)

print(f"OK: {count} relaxed mypy overrides (budget: {OVERRIDE_BUDGET})")
