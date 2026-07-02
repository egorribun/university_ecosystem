import datetime

from app.utils.uuid_v7 import extract_timestamp_from_uuid_v7, generate_uuid7


def test_uuid7_edge_cases():
    # 1. dt with timezone
    dt_aware = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
    u_aware = generate_uuid7(dt=dt_aware)
    assert u_aware.version == 7
    ts_aware = extract_timestamp_from_uuid_v7(u_aware)
    assert abs((ts_aware - dt_aware).total_seconds()) < 0.01

    # 2. dt without timezone (naive)
    dt_naive = datetime.datetime(2026, 1, 1, 12, 0, 0)
    u_naive = generate_uuid7(dt=dt_naive)
    assert u_naive.version == 7
