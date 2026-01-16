import sys

import pytest

# Redirect stdout and stderr to a file
with open("clean_test_log.txt", "w", encoding="utf-8") as f:
    sys.stdout = f
    sys.stderr = f
    exit_code = pytest.main(
        ["-vv", "--tb=short", "--color=no", "tests/test_auth_recovery_codes.py"]
    )

sys.exit(exit_code)
