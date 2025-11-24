# Test Fixes Needed

The backend refactoring (Service Layer extraction) has moved business logic from `app/api/users.py` to `app/services/user_service.py` and `app/services/auth_service.py`.
This has caused existing tests to fail because they were mocking internal functions in `app/api/users.py` that no longer exist or are no longer called directly.

## Required Updates

1.  **Update Mock Targets**:
    - Tests patching `app.api.users.save_upload` should now patch `app.services.user_service.save_upload` (or `delete_static_file`).
    - Tests patching `app.api.users._send_reset_email_blocking` should now patch `app.services.auth_service._send_reset_email_blocking`.
    - Tests patching `app.api.users.secrets` should patch `app.services.auth_service.secrets`.

2.  **Update Imports**:
    - Tests importing internal helpers like `_hash_token` or `_attach_pending_email` from `app.api.users` should now import them from `app.services.auth_service`.

3.  **Files Requiring Attention**:
    - `tests/test_user_profile_update.py` (Partially fixed, but check for others)
    - `tests/test_audit_logs.py` (Fixed imports, but check logic)
    - `tests/test_users_profile_cache.py`
    - Any test file using `monkeypatch` on `app.api.users`.

## Recommendation
Run tests with `pytest -vv` to see the exact `AttributeError` or `ImportError` and update the mock paths accordingly.
