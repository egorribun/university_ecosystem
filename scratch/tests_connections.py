import socket


def test_port(host, port):
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        return True
    except Exception as e:
        print(f"Failed to connect to {host}:{port} - {e}")
        return False


print("Testing connections from host:")
for ip in ["127.0.0.1", "::1", "localhost"]:
    print(f"\nTrying {ip}:")
    pg_ok = test_port(ip, 15432)
    redis_ok = test_port(ip, 16379)
    spicedb_ok = test_port(ip, 15052)
    print(f"Postgres (15432): {'OK' if pg_ok else 'FAILED'}")
    print(f"Redis/Valkey (16379): {'OK' if redis_ok else 'FAILED'}")
    print(f"SpiceDB (15052): {'OK' if spicedb_ok else 'FAILED'}")
