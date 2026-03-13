import inspect

from app.auth.security import _validate_password_policy


def test_validate_password_is_not_a_coroutine():
    """PERF-W5-02: Ensure _validate_password_policy must remain synchronous."""
    assert not inspect.iscoroutinefunction(_validate_password_policy), (
        "PERF-W5-02: _validate_password_policy must remain synchronous to prevent "
        "accidental event loop blocking without executor offload."
    )
