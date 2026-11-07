"""Check consistency of private, operator-collected NetworkPolicy evidence.

This program never contacts a cluster and does not collect credentials, attach a
container, rotate keys, verify provenance signatures, or prove a CNI verdict.
Its zero exit code means only that the supplied records are internally
consistent and eligible for owner review. It cannot establish audit closure.

Schema and synthetic examples are in test_aud169_188_189_evidence.py. Keep real
receipts and raw observations private, outside the repository; store no tokens,
key material, credentials, or Secret values. All digests below identify retained
raw evidence; the owner must independently authenticate and inspect it.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
CONTAINER_ID = re.compile(r"[a-z][a-z0-9+.-]*://[A-Za-z0-9._-]+\Z")
NETWORK_NAMESPACE = re.compile(r"net:\[[0-9]+\]\Z")
METHOD = "/file_processor.v1.FileProcessingService/ProcessFile"
REQUIRED_DENIALS = {
    "dns_udp": ("UDP", 53),
    "dns_tcp": ("TCP", 53),
    "https_private_pod": ("TCP", 443),
    "https_private_service": ("TCP", 443),
    "https_link_local": ("TCP", 443),
}
PRIVATE = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "fc00::/7",
    )
)
LINK_LOCAL = tuple(
    ipaddress.ip_network(value) for value in ("169.254.0.0/16", "fe80::/10")
)


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("missing or inconsistent evidence")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def digest(value: Any) -> bool:
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def time_utc(value: Any) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"))
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0))
    return parsed.astimezone(UTC)


def ip(value: Any, family: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    address = ipaddress.ip_address(value)
    require(
        (address.version == 4 and family == "IPv4")
        or (address.version == 6 and family == "IPv6")
    )
    require(
        not address.is_unspecified
        and not address.is_multicast
        and not address.is_loopback
    )
    return address


def in_networks(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address, values: tuple | list
) -> bool:
    return any(
        address.version == network.version and address in network for network in values
    )


def same_process(before: dict[str, Any], after: dict[str, Any], family: str) -> None:
    for item in (before, after):
        require(nonempty(item["uid"]) and nonempty(item["node"]))
        require(
            isinstance(item["container_id"], str)
            and CONTAINER_ID.fullmatch(item["container_id"]) is not None
        )
        require(type(item["restart_count"]) is int and item["restart_count"] >= 0)
        require(digest(item["image_digest"]))
        require(item["host_network"] is False)
        require(
            isinstance(item["diagnostic_container_id"], str)
            and CONTAINER_ID.fullmatch(item["diagnostic_container_id"]) is not None
        )
        require(
            item["diagnostic_container_id"] != item["container_id"]
            and digest(item["diagnostic_image_digest"])
        )
        require(
            isinstance(item["pod_network_namespace"], str)
            and NETWORK_NAMESPACE.fullmatch(item["pod_network_namespace"]) is not None
        )
        require(item["pod_network_namespace"] == item["diagnostic_network_namespace"])
        require(digest(item["network_namespace_evidence_digest"]))
        require(
            item["diagnostic_privileged"] is False
            and item["diagnostic_run_as_non_root"] is True
        )
        require(item["diagnostic_allow_privilege_escalation"] is False)
        require(
            item["diagnostic_host_mounts"] == []
            and item["diagnostic_added_capabilities"] == []
        )
        ip(item["ip"], family)
        require(time_utc(item["started_at"]) <= time_utc(item["observed_at"]))
    identity_fields = (
        "uid",
        "node",
        "ip",
        "container_id",
        "restart_count",
        "started_at",
        "image_digest",
        "diagnostic_container_id",
        "diagnostic_image_digest",
        "pod_network_namespace",
    )
    require(all(before[key] == after[key] for key in identity_fields))
    require(time_utc(before["observed_at"]) < time_utc(after["observed_at"]))


def environment(receipt: dict[str, Any], expected_sha: str) -> dict[str, Any]:
    require(isinstance(expected_sha, str) and SHA40.fullmatch(expected_sha) is not None)
    require(
        receipt["source_sha"] == expected_sha
        and receipt["image_source_sha"] == expected_sha
    )
    require(
        receipt["source_tree_clean"] is True
        and digest(receipt["image_provenance_digest"])
    )
    require(digest(receipt["image_digest"]))
    env = receipt["environment"]
    require(
        all(
            nonempty(env[key])
            for key in ("name", "cluster_uid", "cni_name", "cni_version")
        )
    )
    require(
        digest(env["policy_inventory_digest"]) and digest(env["cni_inventory_digest"])
    )
    require(isinstance(env["policy_uids"], list) and bool(env["policy_uids"]))
    require(all(nonempty(value) for value in env["policy_uids"]))
    families = env["families"]
    require(
        isinstance(families, list)
        and bool(families)
        and len(set(families)) == len(families)
    )
    require(set(families) <= {"IPv4", "IPv6"})
    for key in ("pod_cidrs", "service_cidrs"):
        require(isinstance(env[key], list) and bool(env[key]))
        networks = [ipaddress.ip_network(value, strict=True) for value in env[key]]
        require(
            all(
                any(net.version == (4 if family == "IPv4" else 6) for net in networks)
                for family in families
            )
        )
    require(isinstance(env["resolver_ips"], list) and bool(env["resolver_ips"]))
    for value in env["resolver_ips"]:
        addr = ipaddress.ip_address(value)
        require(("IPv4" if addr.version == 4 else "IPv6") in families)
    return env


def probe(
    case: dict[str, Any], env: dict[str, Any], expected_name: str, family: str
) -> str:
    require(case["name"] == expected_name and case["family"] == family)
    transport, port = (case["transport"], case["destination_port"])
    if expected_name in REQUIRED_DENIALS:
        require((transport, port) == REQUIRED_DENIALS[expected_name])
    else:
        require(transport == "TCP" and type(port) is int and 1 <= port <= 65535)
    destination = ip(case["destination_ip"], family)
    if expected_name.startswith("dns_"):
        require(
            str(destination)
            not in [str(ipaddress.ip_address(value)) for value in env["resolver_ips"]]
        )
    if expected_name in ("https_private_pod", "https_private_service"):
        require(in_networks(destination, PRIVATE))
        cidr_key = (
            "pod_cidrs" if expected_name == "https_private_pod" else "service_cidrs"
        )
        require(
            in_networks(
                destination, [ipaddress.ip_network(value) for value in env[cidr_key]]
            )
        )
    if expected_name == "https_link_local":
        require(in_networks(destination, LINK_LOCAL))
    if expected_name == "https_private_service":
        # An arbitrary balancing choice could send the controls and denial to
        # different listeners. The isolated test Service has one ready endpoint
        # and its EndpointSlice must be unchanged across the experiment.
        require(digest(case["endpoint_slice_digest"]))
        require(case["endpoint_slice_after_digest"] == case["endpoint_slice_digest"])
        endpoints = case["service_endpoints"]
        require(isinstance(endpoints, list) and len(endpoints) == 1)
        endpoint = endpoints[0]
        require(endpoint["ready"] is True and nonempty(endpoint["uid"]))
        require(type(endpoint["port"]) is int and 1 <= endpoint["port"] <= 65535)
        require(
            in_networks(
                ip(endpoint["ip"], family),
                [ipaddress.ip_network(value) for value in env["pod_cidrs"]],
            )
        )

    source, control = case["source_before"], case["control_before"]
    same_process(source, case["source_after"], family)
    same_process(control, case["control_after"], family)
    require(source["uid"] != control["uid"] and source["ip"] != control["ip"])
    require(
        source["node"] != control["node"]
        or source["pod_network_namespace"] != control["pod_network_namespace"]
    )
    pod_cidrs = [ipaddress.ip_network(value) for value in env["pod_cidrs"]]
    require(in_networks(ip(source["ip"], family), pod_cidrs))
    require(in_networks(ip(control["ip"], family), pod_cidrs))
    records = (case["pre"], case["blocked"], case["post"])
    for attempt, actor, succeeds in zip(
        records, (control, source, control), (True, False, True), strict=True
    ):
        require(
            attempt["source_uid"] == actor["uid"]
            and attempt["source_ip"] == actor["ip"]
        )
        require(
            attempt["destination_ip"] == case["destination_ip"]
            and attempt["destination_port"] == port
        )
        require(attempt["transport"] == transport and digest(attempt["raw_digest"]))
        require(
            type(attempt["exit_code"]) is int
            and ((attempt["exit_code"] == 0) == succeeds)
        )
        require(time_utc(attempt["started_at"]) <= time_utc(attempt["finished_at"]))
        if succeeds:
            if expected_name.startswith("dns_"):
                query = case["query"]
                require(all(nonempty(query[key]) for key in ("name", "type", "answer")))
                require(attempt["response"] == query)
            else:
                require(attempt["response"] == "connected")

    pre, blocked, post = records
    require(time_utc(pre["finished_at"]) <= time_utc(blocked["started_at"]))
    require(time_utc(blocked["finished_at"]) <= time_utc(post["started_at"]))
    require(
        time_utc(post["finished_at"]) - time_utc(pre["started_at"])
        <= timedelta(seconds=30)
    )
    for before, after in (
        (source, case["source_after"]),
        (control, case["control_after"]),
    ):
        require(time_utc(before["observed_at"]) <= time_utc(pre["started_at"]))
        require(time_utc(after["observed_at"]) >= time_utc(post["finished_at"]))
    listener_before, listener_after = case["listener_before"], case["listener_after"]
    require(
        nonempty(listener_before["uid"])
        and listener_before["uid"] not in (source["uid"], control["uid"])
    )
    require(
        listener_before["uid"] == listener_after["uid"]
        and listener_before["ip"] == listener_after["ip"]
    )
    require(
        digest(listener_before["raw_digest"]) and digest(listener_after["raw_digest"])
    )
    require(time_utc(listener_before["observed_at"]) <= time_utc(pre["started_at"]))
    require(time_utc(listener_after["observed_at"]) >= time_utc(post["finished_at"]))
    listener_ip = ip(listener_before["ip"], family)
    if expected_name == "https_private_service":
        require(
            listener_before["uid"] == endpoint["uid"]
            and str(listener_ip) == endpoint["ip"]
        )
    else:
        require(listener_ip == destination)

    verdict = case["verdict"]
    require(
        verdict["source_uid"] == source["uid"] and verdict["source_ip"] == source["ip"]
    )
    require(verdict["transport"] == transport and verdict["direction"] == "egress")
    require(
        verdict["action"] in ("drop", "reject")
        and verdict["policy_uid"] in env["policy_uids"]
    )
    require(digest(verdict["raw_digest"]))
    require(
        time_utc(blocked["started_at"])
        <= time_utc(verdict["timestamp"])
        <= time_utc(blocked["finished_at"])
    )
    observed = (verdict["destination_ip"], verdict["destination_port"])
    if observed != (case["destination_ip"], port):
        require(expected_name == "https_private_service")
        require((endpoint["ip"], endpoint["port"]) == observed)
    return source["uid"]


def grpc_event(
    event: dict[str, Any], state: dict[str, Any], token_ref: str, status: str
) -> datetime:
    require(
        event["pod_uid"] == state["uid"]
        and event["container_id"] == state["container_id"]
    )
    require(event["destination_ip"] == state["ip"] and event["method"] == METHOD)
    require(event["request"] == "empty" and event["token_ref"] == token_ref)
    require(
        event["status"] == status
        and digest(event["raw_digest"])
        and digest(event["token_digest"])
    )
    expected_message = (
        "id is required" if status == "InvalidArgument" else "invalid token"
    )
    require(event["message"] == expected_message)
    return time_utc(event["timestamp"])


def jwks_evidence(data: dict[str, Any], image_digest: str) -> dict[str, dict[str, Any]]:
    key_a, key_b = data["key_a"], data["key_b"]
    require(nonempty(key_a) and nonempty(key_b) and key_a != key_b)
    configured_url = data["configured_url"]
    require(
        nonempty(configured_url)
        and "\r" not in configured_url
        and "\n" not in configured_url
    )
    parsed_url = urlsplit(configured_url)
    require(
        parsed_url.scheme in ("http", "https")
        and bool(parsed_url.hostname)
        and parsed_url.path.startswith("/")
    )
    require(
        parsed_url.username is None
        and parsed_url.password is None
        and not parsed_url.query
        and not parsed_url.fragment
    )
    require(parsed_url.port is None or 1 <= parsed_url.port <= 65535)
    require(type(data["internal_mtls_enabled"]) is bool)
    if data["internal_mtls_enabled"]:
        require(parsed_url.scheme == "https")
    old, new = data["published_before"], data["published_after"]
    require(digest(old["raw_digest"]) and digest(new["raw_digest"]))
    require(digest(new["jwks_document_digest"]))
    for publication in (old, new):
        keys = publication["keys"]
        require(
            isinstance(keys, list) and bool(keys) and all(nonempty(key) for key in keys)
        )
        require(len(keys) == len(set(keys)))
    require(key_a in old["keys"] and key_b not in old["keys"])
    require(key_a in new["keys"] and key_b in new["keys"])
    old_at, publish_at = time_utc(old["at"]), time_utc(new["at"])
    require(old_at < publish_at)
    interval = data["refresh_interval_seconds"]
    require(type(interval) is int and 1 <= interval <= 86400)
    token = data["token_b"]
    require(
        nonempty(token["ref"]) and nonempty(token["jti_ref"]) and token["key"] == key_b
    )
    require(digest(token["token_digest"]))
    require(
        nonempty(data["expected_issuer"]) and token["issuer"] == data["expected_issuer"]
    )
    require(
        nonempty(data["expected_audience"])
        and token["audience"] == data["expected_audience"]
    )
    require(
        token["active"] is True
        and token["revoked"] is False
        and token["signature_valid"] is True
    )
    require(digest(token["validation_digest"]))
    issued, not_before, expires = (
        time_utc(token[key]) for key in ("issued_at", "not_before", "expires_at")
    )
    require(issued <= publish_at and not_before <= publish_at < expires)
    replicas = data["replicas"]
    expected = data["expected_replica_uids"]
    require(
        isinstance(replicas, list)
        and bool(replicas)
        and isinstance(expected, list)
        and bool(expected)
    )
    require(
        all(nonempty(uid) for uid in expected) and len(expected) == len(set(expected))
    )
    seen: dict[str, dict[str, Any]] = {}
    for replica in replicas:
        before, after = replica["before"], replica["after"]
        family = "IPv4" if ipaddress.ip_address(before["ip"]).version == 4 else "IPv6"
        same_process(before, after, family)
        require(before["image_digest"] == image_digest and before["uid"] not in seen)
        seen[before["uid"]] = before
        token_a = replica["key_a_before"]["token_ref"]
        require(nonempty(token_a) and token_a != token["ref"])
        a_before = grpc_event(
            replica["key_a_before"], before, token_a, "InvalidArgument"
        )
        b_before = grpc_event(
            replica["key_b_before"], before, token["ref"], "Unauthenticated"
        )
        b_after = grpc_event(
            replica["key_b_after"], before, token["ref"], "InvalidArgument"
        )
        a_after = grpc_event(replica["key_a_after"], before, token_a, "InvalidArgument")
        require(
            replica["key_a_before"]["token_digest"]
            == replica["key_a_after"]["token_digest"]
        )
        require(replica["key_b_before"]["token_digest"] == token["token_digest"])
        require(replica["key_b_after"]["token_digest"] == token["token_digest"])
        require(old_at <= a_before < publish_at and old_at <= b_before < publish_at)
        require(not_before <= b_before and issued <= b_before and b_after < expires)
        require(time_utc(before["observed_at"]) <= min(a_before, b_before))
        require(time_utc(after["observed_at"]) >= max(a_after, b_after))
        fetch = replica["fetch"]
        require(
            fetch["pod_uid"] == before["uid"]
            and fetch["container_id"] == before["container_id"]
        )
        require(
            fetch["source_ip"] == before["ip"]
            and fetch["status"] == 200
            and fetch["redirected"] is False
        )
        require(
            fetch["url"] == configured_url
            and fetch["jwks_document_digest"] == new["jwks_document_digest"]
        )
        if parsed_url.scheme == "https":
            require(fetch["tls_verified"] is True)
        if data["internal_mtls_enabled"]:
            require(fetch["client_identity_verified"] is True)
        require(digest(fetch["raw_digest"]))
        fetched = time_utc(fetch["timestamp"])
        # Five seconds for the actual request timeout plus bounded scheduler slack.
        require(publish_at <= fetched <= publish_at + timedelta(seconds=interval + 35))
        require(fetched <= b_after and publish_at <= a_after)
    require(set(seen) == set(expected))
    return seen


def assess(receipt: Any, expected_sha: str) -> list[str]:
    """Return non-secret reason codes; empty means consistency, not proof."""
    errors: list[str] = []
    try:
        env = environment(receipt, expected_sha)
    except (KeyError, TypeError, ValueError, OverflowError):
        return ["source_or_environment_incomplete"]
    try:
        replicas = jwks_evidence(receipt["jwks"], receipt["image_digest"])
    except (KeyError, TypeError, ValueError, OverflowError):
        errors.append("jwks_incomplete")
        replicas = {}
    for family in env["families"]:
        try:
            canaries = [
                case for case in receipt["canaries"] if case["family"] == family
            ]
            require(len(canaries) == 1)
            canary_source = probe(canaries[0], env, "canary", family)
            require(
                canary_source not in replicas
                and canaries[0]["control_before"]["uid"] not in replicas
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append("cni_canary_incomplete:" + family)
        for name in REQUIRED_DENIALS:
            try:
                cases = [
                    case
                    for case in receipt["egress_denials"]
                    if case["family"] == family and case["name"] == name
                ]
                require(len(cases) == 1)
                uid = probe(cases[0], env, name, family)
                require(uid in replicas)
                source = cases[0]["source_before"]
                process_fields = (
                    "uid",
                    "node",
                    "container_id",
                    "restart_count",
                    "started_at",
                    "image_digest",
                )
                require(
                    all(
                        source[field] == replicas[uid][field]
                        for field in process_fields
                    )
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                errors.append("egress_incomplete:" + family + ":" + name)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "receipt",
        type=Path,
        help="private sanitized JSON receipt, kept outside the repository",
    )
    parser.add_argument(
        "--expected-source",
        required=True,
        help="exact expected 40-character source commit",
    )
    args = parser.parse_args()
    try:
        with args.receipt.open("r", encoding="utf-8") as stream:
            receipt = json.load(stream)
        errors = assess(receipt, args.expected_source)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        print("incomplete: receipt could not be read", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print("incomplete: " + error, file=sys.stderr)
        return 1
    print(
        "Internally consistent; independent owner and CNI review is still required. Not audit acceptance."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
