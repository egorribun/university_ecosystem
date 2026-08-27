#!/usr/bin/env python3
"""Create an exact-SHA image tag once, or safely reuse identical content."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_SUBJECT = re.compile(r"^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+/[a-z0-9_.-]+$")
_FINAL_REF = re.compile(
    r"^(ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+/[a-z0-9_.-]+):([0-9a-f]{40})$"
)
_MANIFEST_UNKNOWN = re.compile(r"\bmanifest unknown\b", re.IGNORECASE)
_MANIFEST_404 = re.compile(
    r"(?:HEAD|GET) request to https://ghcr\.io/v2/.+/manifests/.+"
    r"\b404 Not Found\b",
    re.IGNORECASE,
)
_FAIL_CLOSED_LOOKUP = re.compile(
    r"\b(?:unauthorized|authentication required|denied|401|403|429|5[0-9]{2}|"
    r"timeout|timed out|network is unreachable|dial tcp|tls handshake)\b",
    re.IGNORECASE,
)

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class PublicationError(RuntimeError):
    """Raised when immutable image publication cannot be proven safe."""


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed docker executable and validated refs
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def _required(
    runner: CommandRunner,
    command: Sequence[str],
    *,
    operation: str,
) -> str:
    result = runner(command)
    if result.returncode != 0:
        raise PublicationError(f"{operation} failed")
    return result.stdout.strip()


def _resolve_remote_digest(
    final_ref: str,
    runner: CommandRunner,
) -> str | None:
    result = runner(
        (
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            final_ref,
            "--format",
            "{{json .Manifest.Digest}}",
        )
    )
    if result.returncode == 0:
        try:
            digest = json.loads(result.stdout.strip())
        except json.JSONDecodeError as error:
            raise PublicationError("remote tag lookup returned invalid JSON") from error
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise PublicationError("remote tag lookup returned an invalid digest")
        return digest

    diagnostic = f"{result.stdout}\n{result.stderr}"
    if _FAIL_CLOSED_LOOKUP.search(diagnostic):
        raise PublicationError("remote tag lookup failed closed")
    if _MANIFEST_UNKNOWN.search(diagnostic) or _MANIFEST_404.search(diagnostic):
        return None
    raise PublicationError("remote tag lookup failed closed")


def _image_id(reference: str, runner: CommandRunner) -> str:
    image_id = _required(
        runner,
        ("docker", "image", "inspect", "--format", "{{.Id}}", reference),
        operation="local image inspection",
    )
    if _IMAGE_ID.fullmatch(image_id) is None:
        raise PublicationError("image inspection returned an invalid image ID")
    return image_id


def _require_remote_matches_local(
    *,
    digest: str,
    local_image_id: str,
    subject_name: str,
    runner: CommandRunner,
) -> None:
    digest_ref = f"{subject_name}@{digest}"
    _required(
        runner,
        ("docker", "pull", digest_ref),
        operation="immutable image pull",
    )
    remote_image_id = _image_id(digest_ref, runner)
    if remote_image_id != local_image_id:
        raise PublicationError(
            "exact-SHA tag already resolves to different image content"
        )


def publish_immutable_image(
    *,
    final_ref: str,
    local_ref: str,
    subject_name: str,
    runner: CommandRunner = _default_runner,
) -> str:
    """Reuse identical remote content or create the exact-SHA tag once."""
    final_match = _FINAL_REF.fullmatch(final_ref)
    if final_match is None or final_match.group(1) != subject_name:
        raise PublicationError("final reference must be a canonical GHCR exact-SHA tag")
    if _SUBJECT.fullmatch(subject_name) is None:
        raise PublicationError("subject name must be a canonical GHCR image name")

    local_image_id = _image_id(local_ref, runner)
    existing_digest = _resolve_remote_digest(final_ref, runner)
    if existing_digest is not None:
        _require_remote_matches_local(
            digest=existing_digest,
            local_image_id=local_image_id,
            subject_name=subject_name,
            runner=runner,
        )
        return existing_digest

    # Repeat the lookup immediately before the only remote mutation. This closes
    # races between serialized release re-runs; a concurrently-created identical
    # tag is reused, while different content fails before docker push can replace it.
    raced_digest = _resolve_remote_digest(final_ref, runner)
    if raced_digest is not None:
        _require_remote_matches_local(
            digest=raced_digest,
            local_image_id=local_image_id,
            subject_name=subject_name,
            runner=runner,
        )
        return raced_digest

    _required(
        runner,
        ("docker", "tag", local_ref, final_ref),
        operation="local exact-SHA tag creation",
    )
    _required(
        runner,
        ("docker", "push", final_ref),
        operation="exact-SHA image publication",
    )
    published_digest = _resolve_remote_digest(final_ref, runner)
    if published_digest is None:
        raise PublicationError("published exact-SHA tag cannot be resolved")
    _require_remote_matches_local(
        digest=published_digest,
        local_image_id=local_image_id,
        subject_name=subject_name,
        runner=runner,
    )
    return published_digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-ref", required=True)
    parser.add_argument("--local-ref", required=True)
    parser.add_argument("--subject-name", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        digest = publish_immutable_image(
            final_ref=args.final_ref,
            local_ref=args.local_ref,
            subject_name=args.subject_name,
        )
    except PublicationError as error:
        parser.error(str(error))
    local_image_id = _image_id(args.local_ref, _default_runner)
    with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"digest={digest}\nlocal_image_id={local_image_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
