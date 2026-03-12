import hashlib
import hmac

import rust_ext


def test_rust_audit_verification():
    print("Testing verify_audit_signature...")

    key = "secret_key_123"
    wrong_key = "wrong_key_456"
    log_data = "log_id_1|user_123|action_delete|2026-03-11T12:00:00Z"

    # Compute signature in Python
    signature = hmac.new(key.encode(), log_data.encode(), hashlib.sha256).hexdigest()

    # Test match
    match = rust_ext.verify_audit_signature([key], log_data, signature)
    print(f"  Valid key match: {match}")
    assert match

    # Test multi-key match
    match_multi = rust_ext.verify_audit_signature([wrong_key, key], log_data, signature)
    print(f"  Multi-key match: {match_multi}")
    assert match_multi

    # Test failure
    no_match = rust_ext.verify_audit_signature([wrong_key], log_data, signature)
    print(f"  Wrong key match: {no_match}")
    assert not no_match

    print("\nRust audit verification passed!")


if __name__ == "__main__":
    test_rust_audit_verification()
