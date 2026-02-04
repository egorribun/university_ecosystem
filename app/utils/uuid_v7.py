import os
import time
import uuid
from datetime import UTC, datetime


def generate_uuid7(dt: datetime | None = None) -> uuid.UUID:
    """
    Generate an RFC 9562 compliant UUID v7.

    If 'dt' is provided, the UUID will be based on that timestamp.
    This is useful for backfilling historical records while maintaining
    temporal locality.
    """
    if dt is None:
        ts_ms = int(time.time() * 1000)
    else:
        ts_ms = int(dt.timestamp() * 1000)

    # 48-bit timestamp (octets 0-5)
    unix_ts_ms = ts_ms & 0xFFFFFFFFFFFF
    ts_bytes = unix_ts_ms.to_bytes(6, "big")

    # Random data for the remaining bits
    # We need 10 bytes more (80 bits), but we'll reserve bits for version/variant
    rand_bytes = os.urandom(10)

    # Octet 6: bits 4-7 are version (0111 = 7)
    # Most significant 4 bits of octet 6
    ver_and_rand = (0x7 << 4) | (rand_bytes[0] & 0x0F)

    # Octet 8: bits 6-7 are variant (10 = RFC 4122 / 9562)
    # Most significant 2 bits of octet 8
    var_and_rand = (0x02 << 6) | (rand_bytes[2] & 0x3F)

    # Reconstruct the 16 bytes
    # [0-5]: ts (6 bytes)
    # [6]: ver_and_rand (1 byte)
    # [7]: rand (1 byte)
    # [8]: var_and_rand (1 byte)
    # [9-15]: rand (7 bytes)

    uuid_bytes = (
        ts_bytes
        + ver_and_rand.to_bytes(1, "big")
        + rand_bytes[1:2]
        + var_and_rand.to_bytes(1, "big")
        + rand_bytes[3:]
    )

    return uuid.UUID(bytes=uuid_bytes)


def extract_timestamp_from_uuid_v7(u: uuid.UUID | str) -> datetime:
    """
    Extract creation timestamp from an RFC 9562 UUID v7.
    """
    if isinstance(u, str):
        u = uuid.UUID(u)

    # UUID v7: first 48 bits are timestamp in ms
    ts_ms = u.int >> 80
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
