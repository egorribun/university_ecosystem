from __future__ import annotations

import json
import os
import pathlib
import re
import sys


def reject_duplicates(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate JSON key")
        data[key] = value
    return data


def verify_inventory(report_path, manifest_path, version):
    path = pathlib.Path(report_path)
    if (
        path.is_symlink()
        or not path.is_file()
        or not 0 < path.stat().st_size <= 4 * 1024 * 1024
    ):
        raise ValueError("missing or oversized stdlib inventory")
    report = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
    )
    results = report["results"]
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError("stdlib inventory must contain one source")
    result = results[0]
    source = result["source"]
    if (
        source.get("type") != "lockfile"
        or pathlib.Path(source["path"]).resolve()
        != pathlib.Path(manifest_path).resolve()
    ):
        raise ValueError("stdlib inventory source mismatch")
    packages = result["packages"]
    if not isinstance(packages, list) or len(packages) != 1:
        raise ValueError("stdlib inventory must contain one package")
    record = packages[0]
    if record["package"] != {"name": "stdlib", "version": version, "ecosystem": "Go"}:
        raise ValueError("stdlib inventory version or package mismatch")
    if record.get("vulnerabilities", []) != [] or record.get("groups", []) != []:
        raise ValueError("stdlib inventory contains vulnerability findings")
    print("Verified Go builder stdlib inventory: " + version)


_TOOLCHAIN_VERSION = re.compile(rb"go([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})")
_FROM_GOLANG = re.compile(rb"^[ \t\r\v\f]*FROM[ \t\r\v\f]+.*golang:")
_BUILDER_IMAGE = re.compile(
    rb"golang:([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})-alpine[0-9.]*@sha256:[0-9a-f]{64}"
)
_TOOLCHAIN_DIRECTIVE = re.compile(rb"^[ \t\r\v\f]*toolchain[ \t\r\v\f]")
_GO_DIRECTIVE_START = re.compile(rb"^[ \t\r\v\f]*go[ \t\r\v\f]")
_GO_VERSION_DIRECTIVE = re.compile(
    rb"^[ \t\r\v\f]*go[ \t\r\v\f]+([0-9]{1,3})\.([0-9]{1,3})(\.([0-9]{1,3}))?"
    rb"([ \t\r\v\f]*(//.*)?)$"
)
_DOCKERFILES = (
    "services/caddy/Dockerfile",
    "services/gateway/Dockerfile",
    "services/ws-hub/Dockerfile",
    "services/file-processor/Dockerfile",
)


def _fail(message=None, *, stderr=False):
    if message:
        print(message, file=sys.stderr if stderr else sys.stdout)
    raise SystemExit(1)


def _regular_nonsymlink(path):
    return not path.is_symlink() and path.is_file()


def _read_shell_lines(path):
    lines = pathlib.Path(path).read_bytes().split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return lines


def preflight(manifest_list_path, toolchain):
    match = _TOOLCHAIN_VERSION.fullmatch(toolchain.encode("utf-8"))
    if not match:
        _fail(
            "::error::Go builder toolchain is not an exact patch release.", stderr=True
        )
    version = toolchain[2:]
    numeric_version = tuple(int(part) for part in match.groups())

    entries = pathlib.Path(manifest_list_path).read_bytes().split(b"\0")
    if entries and entries[-1] == b"":
        entries.pop()
    manifests = [os.fsdecode(path) for path in entries]
    if not manifests:
        _fail("::error::No tracked Go service manifests were discovered.", stderr=True)
    seen = set()
    for manifest in manifests:
        if not _regular_nonsymlink(pathlib.Path(manifest)) or manifest in seen:
            _fail()
        seen.add(manifest)

    for dockerfile in _DOCKERFILES:
        path = pathlib.Path(dockerfile)
        if not _regular_nonsymlink(path):
            _fail()
        builders = 0
        for line in _read_shell_lines(path):
            if not _FROM_GOLANG.match(line):
                continue
            tokens = re.split(rb"[ \t]+", line.strip(b" \t"))
            image = tokens[1] if len(tokens) > 1 else b""
            builder = _BUILDER_IMAGE.fullmatch(image)
            if not builder or builder.group(1).decode("ascii") != version:
                _fail(
                    "::error::A Go builder is unpinned or differs from the scanner toolchain.",
                    stderr=True,
                )
            builders += 1
        if builders == 0:
            _fail(
                "::error::A service Dockerfile has no checked Go builder.", stderr=True
            )

    for manifest in ("go.mod", "gen/go/go.mod", *manifests):
        manifest = pathlib.Path(manifest)
        if not _regular_nonsymlink(manifest):
            _fail()
        directives = 0
        for line in _read_shell_lines(manifest):
            if _TOOLCHAIN_DIRECTIVE.match(line):
                _fail(
                    "::error::An explicit Go toolchain directive needs review.",
                    stderr=True,
                )
            if not _GO_DIRECTIVE_START.match(line):
                continue
            directive = _GO_VERSION_DIRECTIVE.fullmatch(line)
            if not directive:
                _fail(
                    "::error::A Go manifest has an invalid version directive.",
                    stderr=True,
                )
            module_version = tuple(
                int(value or b"0")
                for value in (
                    directive.group(1),
                    directive.group(2),
                    directive.group(4),
                )
            )
            if module_version > numeric_version:
                _fail(
                    "::error::A Go manifest requires a newer toolchain than the builder.",
                    stderr=True,
                )
            directives += 1
        if directives != 1:
            _fail()
    print(version)


def main(argv):
    if argv and argv[0] == "--preflight":
        manifest_list_path, toolchain = argv[1:]
        preflight(manifest_list_path, toolchain)
        return
    report_path, manifest_path, version = argv
    verify_inventory(report_path, manifest_path, version)


if __name__ == "__main__":
    main(sys.argv[1:])
