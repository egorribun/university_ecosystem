"""Build and verify immutable pytest shard test-universe manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn

SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "shard_id",
        "num_shards",
        "all_nodeids",
        "selected_nodeids",
        "all_count",
        "selected_count",
        "all_sha256",
        "selected_sha256",
    }
)


class ManifestError(ValueError):
    """Raised when a pytest shard manifest is unsafe or incomplete."""


def _reject_json_constant(value: str) -> NoReturn:
    raise ManifestError(f"invalid JSON constant: {value}")


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical_nodeids(
    value: object, field: str, *, require_sorted: bool = False
) -> list[str]:
    if not isinstance(value, list):
        raise ManifestError(f"{field} must be an array")
    nodeids: list[str] = []
    for index, nodeid in enumerate(value):
        if not isinstance(nodeid, str) or not nodeid:
            raise ManifestError(f"{field}[{index}] must be a non-empty string")
        nodeids.append(nodeid)
    if len(nodeids) != len(set(nodeids)):
        raise ManifestError(f"{field} contains duplicate node IDs")
    canonical = sorted(nodeids)
    if require_sorted and nodeids != canonical:
        raise ManifestError(f"{field} must be sorted canonically")
    return canonical


def _nodeids_digest(nodeids: Sequence[str]) -> str:
    payload = json.dumps(
        list(nodeids), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ManifestError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ManifestError(f"{field} must be a non-negative integer")
    return value


def build_manifest(
    *,
    shard_id: int,
    num_shards: int,
    all_nodeids: Sequence[str],
    selected_nodeids: Sequence[str],
) -> dict[str, object]:
    """Build a canonical manifest for one post-collection shard."""

    if isinstance(shard_id, bool) or not isinstance(shard_id, int):
        raise ManifestError("shard_id must be an integer")
    if shard_id < 0:
        raise ManifestError("shard_id must be non-negative")
    shard_count = _positive_int(num_shards, "num_shards")
    if shard_id >= shard_count:
        raise ManifestError("shard_id must be within num_shards")

    all_ids = sorted(_canonical_nodeids(list(all_nodeids), "all_nodeids"))
    if not all_ids:
        raise ManifestError("all_nodeids must not be empty")
    selected_ids = sorted(
        _canonical_nodeids(list(selected_nodeids), "selected_nodeids")
    )
    all_set = set(all_ids)
    selected_set = set(selected_ids)
    if not selected_set <= all_set:
        unexpected = sorted(selected_set - all_set)
        raise ManifestError(
            "selected_nodeids contains IDs outside the collected test universe: "
            f"{unexpected[:5]}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "shard_id": shard_id,
        "num_shards": shard_count,
        "all_nodeids": all_ids,
        "selected_nodeids": selected_ids,
        "all_count": len(all_ids),
        "selected_count": len(selected_ids),
        "all_sha256": _nodeids_digest(all_ids),
        "selected_sha256": _nodeids_digest(selected_ids),
    }


def write_manifest(
    path: Path,
    *,
    shard_id: int,
    num_shards: int,
    all_nodeids: Sequence[str],
    selected_nodeids: Sequence[str],
) -> dict[str, object]:
    """Write a manifest atomically and return its canonical document."""

    document = build_manifest(
        shard_id=shard_id,
        num_shards=num_shards,
        all_nodeids=all_nodeids,
        selected_nodeids=selected_nodeids,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(document, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except (OSError, TypeError, ValueError) as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise ManifestError(f"unable to write pytest shard manifest {path}") from error
    return document


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except ManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"unable to read pytest shard manifest {path}") from error
    if not isinstance(value, dict):
        raise ManifestError(f"pytest shard manifest {path} must be an object")
    missing = sorted(MANIFEST_FIELDS - set(value))
    unexpected = sorted(set(value) - MANIFEST_FIELDS)
    if missing:
        raise ManifestError(f"pytest shard manifest {path} missing fields: {missing}")
    if unexpected:
        raise ManifestError(
            f"pytest shard manifest {path} has unexpected fields: {unexpected}"
        )
    return value


def _validate_manifest(document: Mapping[str, object], path: Path) -> dict[str, object]:
    schema_version = document["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise ManifestError(f"pytest shard manifest {path} has unsupported schema")
    shard_id = document["shard_id"]
    if isinstance(shard_id, bool) or not isinstance(shard_id, int):
        raise ManifestError(f"pytest shard manifest {path} shard_id is invalid")
    num_shards = _positive_int(document["num_shards"], f"{path}.num_shards")
    if shard_id < 0 or shard_id >= num_shards:
        raise ManifestError(f"pytest shard manifest {path} shard_id is out of range")

    all_ids = _canonical_nodeids(
        document["all_nodeids"], f"{path}.all_nodeids", require_sorted=True
    )
    if not all_ids:
        raise ManifestError(f"pytest shard manifest {path} has an empty test universe")
    selected_ids = _canonical_nodeids(
        document["selected_nodeids"],
        f"{path}.selected_nodeids",
        require_sorted=True,
    )
    if not set(selected_ids) <= set(all_ids):
        raise ManifestError(
            f"pytest shard manifest {path} selected node IDs exceed collected universe"
        )
    all_count = _nonnegative_int(document["all_count"], f"{path}.all_count")
    selected_count = _nonnegative_int(
        document["selected_count"], f"{path}.selected_count"
    )
    if all_count != len(all_ids):
        raise ManifestError(f"{path}.all_count does not match all_nodeids")
    if selected_count != len(selected_ids):
        raise ManifestError(f"{path}.selected_count does not match selected_nodeids")
    for field, nodeids in (("all_sha256", all_ids), ("selected_sha256", selected_ids)):
        digest = document[field]
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise ManifestError(f"{path}.{field} is not a SHA-256 digest")
        if digest != _nodeids_digest(nodeids):
            raise ManifestError(f"{path}.{field} does not match node IDs")
    return {
        "shard_id": shard_id,
        "num_shards": num_shards,
        "all_nodeids": all_ids,
        "selected_nodeids": selected_ids,
        "all_sha256": document["all_sha256"],
    }


def verify_manifests(
    paths: Sequence[Path], *, expected_shards: int
) -> dict[str, object]:
    """Verify one complete, disjoint manifest per expected shard."""

    shard_count = _positive_int(expected_shards, "expected_shards")
    if len(paths) != shard_count:
        raise ManifestError(
            f"expected exactly {shard_count} pytest shard manifests, found {len(paths)}"
        )
    documents: list[dict[str, object]] = []
    seen_shards: set[int] = set()
    for path in paths:
        document = _validate_manifest(_load_manifest(path), path)
        if document["num_shards"] != shard_count:
            raise ManifestError(
                f"pytest shard manifest {path} has unexpected num_shards"
            )
        shard_id = int(document["shard_id"])
        if shard_id in seen_shards:
            raise ManifestError(f"duplicate pytest shard manifest for shard {shard_id}")
        seen_shards.add(shard_id)
        documents.append(document)
    missing_shards = sorted(set(range(shard_count)) - seen_shards)
    if missing_shards:
        raise ManifestError(f"missing pytest shard manifests: {missing_shards}")
    documents.sort(key=lambda document: int(document["shard_id"]))

    collected_universe = list(documents[0]["all_nodeids"])
    collected_set = set(collected_universe)
    all_digest = documents[0]["all_sha256"]
    for document in documents[1:]:
        if document["all_nodeids"] != collected_universe:
            raise ManifestError("collected node-id universe differs across shards")
        if document["all_sha256"] != all_digest:
            raise ManifestError(
                "collected node-id universe digest differs across shards"
            )

    selected_owner: dict[str, int] = {}
    for document in documents:
        shard_id = int(document["shard_id"])
        for nodeid in document["selected_nodeids"]:
            if nodeid in selected_owner:
                raise ManifestError(
                    "test-universe selected node ID appears in more than one shard: "
                    f"{nodeid} (shards {selected_owner[nodeid]} and {shard_id})"
                )
            selected_owner[nodeid] = shard_id
    selected_set = set(selected_owner)
    if selected_set != collected_set:
        missing = sorted(collected_set - selected_set)
        unexpected = sorted(selected_set - collected_set)
        raise ManifestError(
            "test-universe selected node-id union differs from collected universe: "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}"
        )
    return {
        "all_count": len(collected_set),
        "selected_count": len(selected_set),
        "all_sha256": all_digest,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-shards", required=True, type=int)
    parser.add_argument(
        "--manifest",
        action="append",
        dest="manifests",
        required=True,
        type=Path,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        result = verify_manifests(
            arguments.manifests, expected_shards=arguments.expected_shards
        )
    except ManifestError as error:
        parser.error(str(error))
    print(
        "Verified pytest shard test universe: "
        f"{result['selected_count']} selected node IDs across "
        f"{arguments.expected_shards} shards"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
