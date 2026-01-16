import sys

import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(["-vv", "--tb=short", "tests/test_auth_recovery_codes.py"]))
