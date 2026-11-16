"""In-cluster programs and manifests for the NetworkPolicy runtime proof.

Stand-in pods run only the Python standard library from the digest-pinned backend
base image. Pod specs carry no credentials: the probe passes any secret on stdin
for a single exec, so it never appears in a manifest, log or receipt.
"""

from __future__ import annotations

from typing import Any

JWKS_WITNESS_READ_LIBRARY_SRC = r"""
import json, os, re, time

_WITNESS_DIR = "/tmp/netpol-jwks-witness"
_WITNESS_KIDS = ["primary", "netpol-rotated"]
_WITNESS_UID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_WITNESS_EPOCH = re.compile(r"[0-9a-f]{16}\Z")

def read_jwks_witness(epoch, uids):
    try:
        if not isinstance(epoch, str) or not _WITNESS_EPOCH.fullmatch(epoch): return {"result": "unavailable"}
        if not isinstance(uids, list) or len(uids) != 2 or len(set(uids)) != 2: return {"result": "unavailable"}
        events = []
        for uid in sorted(uids):
            if not isinstance(uid, str) or not _WITNESS_UID.fullmatch(uid): return {"result": "unavailable"}
            with open(os.path.join(_WITNESS_DIR, epoch, uid + ".json"), "rb") as source:
                raw = source.read(1025)
            if len(raw) > 1024: return {"result": "unavailable"}
            event = json.loads(raw)
            if not isinstance(event, dict) or set(event) != {"pod_uid", "epoch", "status", "key_ids", "monotonic_ns"}: return {"result": "unavailable"}
            if event["pod_uid"] != uid or event["epoch"] != epoch or event["status"] != 200 or event["key_ids"] != _WITNESS_KIDS: return {"result": "unavailable"}
            if type(event["monotonic_ns"]) is not int or event["monotonic_ns"] <= 0: return {"result": "unavailable"}
            events.append(event)
        return {"result": "observed", "events": events, "collected_monotonic_ns": time.monotonic_ns()}
    except Exception:
        return {"result": "unavailable"}
"""


JWKS_WITNESS_COMMON_SRC = (
    JWKS_WITNESS_READ_LIBRARY_SRC
    + r"""
import ipaddress, tempfile

_JWKS_PATH = "/tmp/jwks.json"

def _witness_atomic(path, value):
    fd, temp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".event-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, separators=(",", ":"))
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def _witness_publish_bytes(path, value):
    fd, temp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".jwks-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(value)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def _witness_first(path, value):
    fd, temp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".event-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, separators=(",", ":"))
        try:
            os.link(temp, path)
        except FileExistsError:
            pass
    finally:
        if os.path.exists(temp): os.unlink(temp)

def _witness_config(config):
    if not isinstance(config, dict) or set(config) != {"epoch", "peers", "key_ids"}:
        return False
    epoch, peers, kids = config["epoch"], config["peers"], config["key_ids"]
    if not isinstance(epoch, str) or not _WITNESS_EPOCH.fullmatch(epoch): return False
    if kids != _WITNESS_KIDS or not isinstance(peers, dict) or len(peers) != 2: return False
    if len(set(peers.values())) != 2: return False
    for ip, uid in peers.items():
        if not isinstance(uid, str) or not _WITNESS_UID.fullmatch(uid): return False
        if not isinstance(ip, str) or str(ipaddress.ip_address(ip)) != ip: return False
    return True

def arm_jwks_witness(config):
    try:
        if not _witness_config(config): return False
        os.makedirs(_WITNESS_DIR, mode=0o700, exist_ok=True)
        os.mkdir(os.path.join(_WITNESS_DIR, config["epoch"]), 0o700)
        _witness_atomic(os.path.join(_WITNESS_DIR, "active.json"), config)
        return True
    except Exception:
        return False

def publish_jwks_document(document, observer=None):
    data = document.encode("utf-8") if isinstance(document, str) else document
    parsed = json.loads(data)
    armed = False
    if observer is not None:
        try:
            with open(_JWKS_PATH, "rb") as source:
                previous = source.read(16385)
            old_keys = json.loads(previous).get("keys")
            new_keys = parsed.get("keys")
            if (len(previous) <= 16384 and isinstance(old_keys, list) and len(old_keys) == 1
                    and old_keys[0].get("kid") == "primary" and isinstance(new_keys, list)
                    and len(new_keys) == 2
                    and sorted(key.get("kid") for key in new_keys) == sorted(_WITNESS_KIDS)):
                armed = arm_jwks_witness(observer)
        except Exception:
            armed = False
    lower_bound = None
    if armed:
        try:
            lower_bound = time.monotonic_ns()
        except Exception:
            armed = False
    _witness_publish_bytes(_JWKS_PATH, data)
    result = {"result": "published"}
    if observer is not None:
        result["observer"] = ({"status": "armed", "publication_lower_bound_ns": lower_bound}
                              if armed else {"status": "unavailable"})
    return result

def record_jwks_witness(request, payload, peer, port):
    try:
        if port != 8000 or len(payload) > 16384: return
        line, separator, _ = request.partition(b"\r\n")
        if not separator or line not in (b"GET /.well-known/jwks.json HTTP/1.1", b"GET /.well-known/jwks.json HTTP/1.0"): return
        with open(os.path.join(_WITNESS_DIR, "active.json"), "rb") as source:
            raw = source.read(4097)
        if len(raw) > 4096: return
        config = json.loads(raw)
        if not _witness_config(config): return
        uid = config["peers"].get(peer)
        if uid is None: return
        document = json.loads(payload)
        keys = document.get("keys")
        if not isinstance(keys, list) or len(keys) != 2: return
        if sorted(key.get("kid") for key in keys) != sorted(_WITNESS_KIDS): return
        event = {"pod_uid": uid, "epoch": config["epoch"], "status": 200,
                 "key_ids": _WITNESS_KIDS, "monotonic_ns": time.monotonic_ns()}
        _witness_first(os.path.join(_WITNESS_DIR, config["epoch"], uid + ".json"), event)
    except Exception:
        return

"""
)


LISTENER_SRC = (
    JWKS_WITNESS_COMMON_SRC
    + r"""
import os, socket, threading
JWKS_PATH = "/tmp/jwks.json"
EMPTY_JWKS = b'{"keys":[]}'

def document():
    try:
        with open(JWKS_PATH, "rb") as handle:
            return handle.read()
    except OSError:
        return EMPTY_JWKS

def handle(conn, peer, port):
    try:
        conn.settimeout(3)
        data = conn.recv(512)
        if data.startswith(b"GET "):
            payload = document()
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         b"Content-Length: " + str(len(payload)).encode() +
                         b"\r\nConnection: close\r\n\r\n" + payload)
            try:
                record_jwks_witness(data, payload, peer, port)
            except Exception:
                pass
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
        conn, peer = s.accept()
        threading.Thread(target=handle, args=(conn, peer[0], port), daemon=True).start()

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
)

# Replaces the JWKS document served by the publisher stand-in. Written atomically.
PUBLISH_SRC = (
    JWKS_WITNESS_COMMON_SRC
    + r"""
import sys
data = sys.stdin.buffer.read()
if sys.argv[1:] == ["observe"]:
    payload = json.loads(data)
    print(json.dumps(publish_jwks_document(payload["document"], payload["observer"])))
else:
    print(json.dumps(publish_jwks_document(data)))
"""
)

JWKS_WITNESS_READ_SRC = (
    JWKS_WITNESS_READ_LIBRARY_SRC
    + r"""
import sys
try:
    payload = json.loads(sys.stdin.buffer.read())
    result = read_jwks_witness(payload["epoch"], payload["uids"])
except Exception:
    result = {"result": "unavailable"}
print(json.dumps(result))
"""
)

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
    host_network: bool = False,
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
            # Host networking is used only for the link-local listener and its
            # control: their traffic is not subject to pod NetworkPolicy.
            "hostNetwork": host_network,
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
