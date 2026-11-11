"""Standalone ZAP hook and strict private same-origin response validation.

Mounted read-only into the scanner. Only a 2xx GET response from the exact
scheme/host/effective-port is accepted, never a report site name or URL prefix.
This proves one observed response in ZAP history, not full active-scan coverage.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

TARGET_PATH = Path("/zap/target.txt")
PROOF_PATH = Path("/zap/wrk/origin-proof.json")
MAX_HEADER = 65536
MAX_MESSAGES = 100


def origin(value: str) -> tuple[str, str, int]:
    """Parse an unambiguous HTTP origin, retaining exact scheme and port."""
    if not isinstance(value, str) or any(
        char.isspace() or ord(char) < 32 for char in value
    ):
        raise ValueError("Invalid response origin")
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or not parts.netloc.isascii()
        or "%" in parts.netloc
        or "\\" in value
        or parts.fragment
        or parts.port == 0
    ):
        raise ValueError("Invalid response origin")
    return (
        parts.scheme,
        parts.hostname.casefold(),
        parts.port or (443 if parts.scheme == "https" else 80),
    )


def _lines(value: Any) -> list[str]:
    if (
        not isinstance(value, str)
        or len(value) > MAX_HEADER
        or not value.endswith("\r\n\r\n")
    ):
        raise ValueError("Invalid HTTP evidence")
    remainder = value.replace("\r\n", "")
    if (
        "\r" in remainder
        or "\n" in remainder
        or any(
            (ord(char) < 32 and char != "\t") or ord(char) == 127 for char in remainder
        )
    ):
        raise ValueError("Invalid HTTP evidence")
    lines = value[:-4].split("\r\n")
    for line in lines[1:]:
        if re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+:[^\r\n]*", line) is None:
            raise ValueError("Invalid HTTP evidence")
    return lines


def validate_proof(proof: dict[str, Any], target: str) -> None:
    """Reject forged origin shortcuts and proxy/error/redirect-only responses."""
    if (
        not isinstance(proof, dict)
        or set(proof)
        != {"schema_version", "message_id", "request_header", "response_header"}
        or type(proof["schema_version"]) is not int
        or proof["schema_version"] != 1
        or not isinstance(proof["message_id"], str)
        or re.fullmatch(r"[1-9][0-9]*", proof["message_id"]) is None
    ):
        raise ValueError("Invalid ZAP origin evidence")
    request = _lines(proof["request_header"])
    response = _lines(proof["response_header"])
    first = re.fullmatch(r"GET (https?://[^ ]+) HTTP/1\.[01]", request[0])
    if (
        first is None
        or re.fullmatch(r"HTTP/1\.[01] 2[0-9]{2}(?: [^\r\n]*)?", response[0]) is None
    ):
        raise ValueError("No successful authorized-origin response")
    expected = origin(target)
    if origin(first.group(1)) != expected:
        raise ValueError("Response does not match authorized origin")
    hosts = [
        line.partition(":")[2].strip()
        for line in request[1:]
        if line.partition(":")[0].casefold() == "host"
    ]
    if len(hosts) != 1 or any(char in hosts[0] for char in "/?#"):
        raise ValueError("Ambiguous request authority")
    if origin(f"{expected[0]}://{hosts[0]}") != expected:
        raise ValueError("Request authority does not match authorized origin")


def zap_pre_shutdown(zap: Any) -> None:
    """Capture one bounded successful response from the real ZAP history API."""
    target = TARGET_PATH.read_text(encoding="utf-8")
    origin(target)
    # CoreAPI baseurl is a raw prefix, not normalized origin matching. Read a
    # bounded history without it and validate each record ourselves. Positive
    # starts are one-based (0 and 1 both select the first record).
    for start in range(1, MAX_MESSAGES + 1):
        messages = zap.core.messages(start=start, count=1)
        if not isinstance(messages, list) or len(messages) > 1:
            raise ValueError("Unexpected ZAP history response")
        if not messages:
            break
        message = messages[0]
        if not isinstance(message, dict):
            raise ValueError("Unexpected ZAP history record")
        proof = {
            "schema_version": 1,
            "message_id": message.get("id"),
            "request_header": message.get("requestHeader"),
            "response_header": message.get("responseHeader"),
        }
        try:
            validate_proof(proof, target)
        except ValueError:
            continue
        descriptor = os.open(PROOF_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(proof, handle, sort_keys=True)
            handle.write("\n")
        return
    raise ValueError("No successful authorized-origin response in bounded ZAP history")
