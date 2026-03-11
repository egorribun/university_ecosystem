import rust_ext
from datetime import UTC, datetime

def test_rust_partition_logic():
    print("Testing get_partition_info...")
    for i in range(3):
        info = rust_ext.get_partition_info("notifications", i)
        print(f"  Offset {i}: {info.name} [{info.start_date} -> {info.end_date}]")
        assert info.name.startswith("notifications_y20")
        assert "T00:00:00+00:00" in info.start_date

    print("\nTesting is_partition_expired...")
    # Test future partition (not expired)
    future_info = rust_ext.get_partition_info("notifications", 1)
    is_expired = rust_ext.is_partition_expired(future_info.name, "notifications", 30)
    print(f"  Future {future_info.name}: expired={is_expired}")
    assert not is_expired

    # Test old partition (mock name from past)
    old_name = "notifications_y2020m01"
    is_expired_old = rust_ext.is_partition_expired(old_name, "notifications", 30)
    print(f"  Old {old_name}: expired={is_expired_old}")
    assert is_expired_old

if __name__ == "__main__":
    test_rust_partition_logic()
    print("\nRust smoke test passed!")
