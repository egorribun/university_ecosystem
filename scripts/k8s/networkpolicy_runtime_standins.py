"""In-cluster programs and manifests for the NetworkPolicy runtime proof.

Stand-in pods run only the Python standard library from the digest-pinned backend
base image. Pod specs carry no credentials: the probe passes any secret on stdin
for a single exec, so it never appears in a manifest, log or receipt.
"""

from __future__ import annotations

from typing import Any

LISTENER_SRC = r"""
import os, socket, threading
JWKS_PATH = "/tmp/jwks.json"
EMPTY_JWKS = b'{"keys":[]}'

def document():
    try:
        with open(JWKS_PATH, "rb") as handle:
            return handle.read()
    except OSError:
        return EMPTY_JWKS

def handle(conn):
    try:
        conn.settimeout(3)
        data = conn.recv(512)
        if data.startswith(b"GET "):
            payload = document()
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         b"Content-Length: " + str(len(payload)).encode() +
                         b"\r\nConnection: close\r\n\r\n" + payload)
    except OSError:
        pass
    finally:
        conn.close()

def tcp(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(64)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()

def udp(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    while True:
        _, addr = s.recvfrom(512)
        s.sendto(b"decoy", addr)

for port in [int(p) for p in os.environ.get("LISTEN_TCP", "").split(",") if p]:
    threading.Thread(target=tcp, args=(port,), daemon=True).start()
for port in [int(p) for p in os.environ.get("LISTEN_UDP", "").split(",") if p]:
    threading.Thread(target=udp, args=(port,), daemon=True).start()
threading.Event().wait()
"""

# Replaces the JWKS document served by the publisher stand-in. Written atomically.
PUBLISH_SRC = r"""
import json, os, sys
data = sys.stdin.buffer.read()
json.loads(data)
temporary = "/tmp/jwks.json.tmp"
with open(temporary, "wb") as handle:
    handle.write(data)
os.replace(temporary, "/tmp/jwks.json")
print(json.dumps({"result": "published"}))
"""

PROBE_SRC = r"""
import json, socket, struct, sys
mode, host, port, timeout = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])

def out(result, **extra):
    extra["result"] = result
    print(json.dumps(extra, sort_keys=True))

def encode_name(name):
    parts = [p.encode("ascii") for p in name.rstrip(".").split(".")]
    return b"".join(bytes([len(p)]) + p for p in parts) + b"\x00"

def skip_name(buf, off):
    while True:
        length = buf[off]
        if length & 0xC0 == 0xC0:
            return off + 2
        if length == 0:
            return off + 1
        off += 1 + length

def recv_exact(sock, count):
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise OSError("short read")
        data += chunk
    return data

def parse(buf):
    qid, flags, qdcount, ancount = struct.unpack("!HHHH", buf[:8])
    off = 12
    for _ in range(qdcount):
        off = skip_name(buf, off) + 4
    answers = []
    for _ in range(ancount):
        off = skip_name(buf, off)
        rtype, _rclass, _ttl, rdlen = struct.unpack("!HHIH", buf[off:off + 10])
        off += 10
        if rtype == 1 and rdlen == 4:
            answers.append(socket.inet_ntoa(buf[off:off + 4]))
        off += rdlen
    return qid, flags, answers

def resp_command(*parts):
    encoded = b"*%d\r\n" % len(parts)
    for part in parts:
        raw = part.encode("utf-8")
        encoded += b"$%d\r\n%s\r\n" % (len(raw), raw)
    return encoded

def read_reply_line(sock):
    line = b""
    while not line.endswith(b"\r\n") and len(line) < 512:
        chunk = sock.recv(1)
        if not chunk:
            raise OSError("short read")
        line += chunk
    return line[:-2].split(b" ", 1)[0].decode("ascii", "replace")

def redis_ping(password):
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        auth = ""
        if password:
            sock.sendall(resp_command("AUTH", password))
            auth = read_reply_line(sock)
        sock.sendall(resp_command("PING"))
        reply = read_reply_line(sock)
    finally:
        sock.close()
    return auth, reply

try:
    if mode == "tcp":
        socket.create_connection((host, port), timeout=timeout).close()
        out("connected")
    elif mode == "http":
        path = sys.argv[5]
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n" % (path, host)).encode("ascii"))
        data = b""
        while b"\r\n" not in data and len(data) < 4096:
            chunk = sock.recv(1024)
            if not chunk:
                break
            data += chunk
        sock.close()
        parts = data.split(b" ", 2)
        status = parts[1].decode("ascii", "replace") if data.startswith(b"HTTP/") and len(parts) > 1 else "none"
        out("http", status=status)
    elif mode in ("dns-udp", "dns-tcp"):
        name = sys.argv[5]
        query_id = 0x5A5A
        query = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0) + encode_name(name) + struct.pack("!HH", 1, 1)
        if mode == "dns-udp":
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(query, (host, port))
            buf = sock.recvfrom(4096)[0]
            sock.close()
        else:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.sendall(struct.pack("!H", len(query)) + query)
            length = struct.unpack("!H", recv_exact(sock, 2))[0]
            buf = recv_exact(sock, length)
            sock.close()
        qid, flags, answers = parse(buf)
        rcode = flags & 0x000F
        if qid == query_id and flags & 0x8000 and rcode == 0:
            out("dns-answer", answers=answers, rcode=rcode)
        else:
            out("dns-bad", rcode=rcode)
    elif mode == "udp-reply":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(b"probe", (host, port))
        sock.recvfrom(512)
        sock.close()
        out("udp-reply")
    elif mode == "redis-ping":
        # The password arrives on stdin only, so it is never in argv or a pod spec.
        auth, reply = redis_ping(sys.stdin.read().strip())
        out("redis-pong" if reply == "+PONG" else "redis-denied", auth=auth, reply=reply)
    else:
        out("error", error="unknown-mode")
except (TimeoutError, socket.timeout):
    out("timeout")
except ConnectionRefusedError:
    out("refused")
except OSError as error:
    out("error", error=type(error).__name__)
"""

# RS256 verification (RSASSA-PKCS1-v1_5 with SHA-256, RFC 8017 section 8.2) in the
# standard library. The token arrives on stdin; the JWKS is fetched from the URL
# argument in this pod's own network namespace, so the enforced policy applies.
VERIFIER_SRC = r"""
import base64, hashlib, hmac, json, sys, time, urllib.request
url, timeout = sys.argv[1], float(sys.argv[2])
DIGEST_INFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")

def out(result, reason=""):
    print(json.dumps({"reason": reason, "result": result}, sort_keys=True))

def b64url_decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

def verify_rs256(modulus, exponent, signing_input, signature):
    key_bytes = (modulus.bit_length() + 7) // 8
    if len(signature) != key_bytes:
        return False
    value = int.from_bytes(signature, "big")
    if value >= modulus:
        return False
    recovered = pow(value, exponent, modulus).to_bytes(key_bytes, "big")
    digest_info = DIGEST_INFO_SHA256 + hashlib.sha256(signing_input).digest()
    padding = key_bytes - len(digest_info) - 3
    expected = b"\x00\x01" + b"\xff" * padding + b"\x00" + digest_info
    return hmac.compare_digest(recovered, expected)

def find_key(jwks, kid):
    for key in jwks.get("keys", []):
        if isinstance(key, dict) and key.get("kid") == kid and key.get("kty") == "RSA":
            return key
    return None

def main():
    parts = sys.stdin.read().strip().split(".")
    if len(parts) != 3:
        return out("rejected", "malformed")
    try:
        header = json.loads(b64url_decode(parts[0]))
        payload = json.loads(b64url_decode(parts[1]))
        signature = b64url_decode(parts[2])
    except (ValueError, TypeError):
        return out("rejected", "malformed")
    if not isinstance(header, dict) or header.get("alg") != "RS256":
        return out("rejected", "alg")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        return out("rejected", "no-kid")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            jwks = json.loads(response.read(65536))
    except (OSError, ValueError):
        return out("rejected", "fetch-failed")
    key = find_key(jwks, kid) if isinstance(jwks, dict) else None
    if key is None or not isinstance(key.get("n"), str) or not isinstance(key.get("e"), str):
        return out("rejected", "unknown-kid")
    modulus = int.from_bytes(b64url_decode(key["n"]), "big")
    exponent = int.from_bytes(b64url_decode(key["e"]), "big")
    signing_input = (parts[0] + "." + parts[1]).encode("ascii")
    if not verify_rs256(modulus, exponent, signing_input, signature):
        return out("rejected", "bad-signature")
    if not isinstance(payload, dict) or not isinstance(payload.get("exp"), (int, float)) or payload["exp"] <= time.time():
        return out("rejected", "expired")
    out("accepted")

main()
"""


def stand_in_pod(
    namespace: str,
    name: str,
    labels: dict[str, str],
    image: str,
    listen_tcp: str = "",
    listen_udp: str = "",
) -> dict[str, Any]:
    env = []
    if listen_tcp:
        env.append({"name": "LISTEN_TCP", "value": listen_tcp})
    if listen_udp:
        env.append({"name": "LISTEN_UDP", "value": listen_udp})
    if listen_tcp or listen_udp:
        command = ["python3", "-u", "-I", "-c", LISTENER_SRC]
    else:
        command = ["sleep", "infinity"]
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "name": "probe",
                    "image": image,
                    "imagePullPolicy": "IfNotPresent",
                    "command": command,
                    "env": env,
                    "securityContext": {"allowPrivilegeEscalation": False},
                }
            ],
        },
    }


def service(
    namespace: str, name: str, selector: dict[str, str], port: int
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "selector": selector,
            "ports": [
                {"name": "probe", "protocol": "TCP", "port": port, "targetPort": port}
            ],
        },
    }
