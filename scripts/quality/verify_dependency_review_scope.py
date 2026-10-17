from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import ssl
import stat
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    build_opener,
)

# The pinned action matches package PURLs by type and name, not version.
# Version scope is enforced against current go.mod pins and the action output.
LICENSE_REF = "LicenseRef-bad-apache-2.0-bsd-3-clause"
KLAUSPOST_LICENSE = "BSD-3-Clause AND Apache-2.0 AND MIT"
CONFIG_PATH = ".github/dependency-review-config.yml"
MAX_DEPENDENCY_COMPARE_BYTES = 8 * 1024 * 1024
DEPENDENCY_COMPARE_PAGE_SIZE = 100
DEPENDENCY_COMPARE_OUTPUT_NAME = "dependency-review-changes.json"
MAX_DEPENDENCY_COMPARE_PAGES = 1000
DEPENDENCY_COMPARE_RETRY_STATUSES = frozenset({429, 502, 503, 504})
DEPENDENCY_COMPARE_MAX_ATTEMPTS = 4
DEPENDENCY_COMPARE_RETRY_BASE_SECONDS = 0.25
DEPENDENCY_COMPARE_MAX_BACKOFF_SECONDS = 1.0
DEPENDENCY_COMPARE_MAX_RETRY_AFTER_SECONDS = 2.0

EXPECTED_MODULES = {
    "services/file-processor/go.mod": {
        "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc": "v0.72.0",
        "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc": "v1.47.0",
        "github.com/klauspost/compress": "v1.20.1",
    },
    "services/gateway/go.mod": {
        "go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin": "v0.72.0",
        "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc": "v1.47.0",
        "github.com/klauspost/compress": "v1.20.1",
    },
    "services/ws-hub/go.mod": {
        "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc": "v1.47.0",
        "github.com/klauspost/compress": "v1.20.1",
    },
}


def _identity(
    manifest: str, name: str, version: str, license_id: str
) -> tuple[str, ...]:
    return (
        "added",
        manifest,
        "gomod",
        name,
        version,
        f"pkg:golang/{name}@{version}",
        license_id,
    )


EXPECTED_ROWS = {
    _identity(
        "services/file-processor/go.mod",
        "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc",
        "0.72.0",
        LICENSE_REF,
    ),
    _identity(
        "services/file-processor/go.mod",
        "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc",
        "1.47.0",
        LICENSE_REF,
    ),
    _identity(
        "services/gateway/go.mod",
        "go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin",
        "0.72.0",
        LICENSE_REF,
    ),
    _identity(
        "services/gateway/go.mod",
        "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc",
        "1.47.0",
        LICENSE_REF,
    ),
    _identity(
        "services/ws-hub/go.mod",
        "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc",
        "1.47.0",
        LICENSE_REF,
    ),
    _identity(
        "services/file-processor/go.mod",
        "github.com/klauspost/compress",
        "1.20.1",
        KLAUSPOST_LICENSE,
    ),
    _identity(
        "services/gateway/go.mod",
        "github.com/klauspost/compress",
        "1.20.1",
        KLAUSPOST_LICENSE,
    ),
    _identity(
        "services/ws-hub/go.mod",
        "github.com/klauspost/compress",
        "1.20.1",
        KLAUSPOST_LICENSE,
    ),
}
TARGET_NAMES = {row[3] for row in EXPECTED_ROWS}
TARGET_PURL_TYPE = "golang"
FIELDS = (
    "change_type",
    "manifest",
    "ecosystem",
    "name",
    "version",
    "package_url",
    "license",
)
# Required fields from ChangeSchema in the action pinned in dependency-review.yml.
REQUIRED_FIELDS = (*FIELDS, "source_repository_url")
PURL_ADDITIONS = Counter(
    {
        "pkg:golang/go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc": 1,
        "pkg:golang/go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin": 1,
        "pkg:golang/go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc": 1,
        "pkg:golang/github.com/klauspost/compress": 1,
    }
)
PURL_REMOVALS = Counter({"pkg:golang/github.com/klauspost/compress@1.20.1": 1})


def _action_row(row: Any) -> tuple[str, ...]:
    if not isinstance(row, dict) or any(field not in row for field in REQUIRED_FIELDS):
        raise ValueError(
            "dependency row does not match the pinned action output schema"
        )
    for field in (
        "change_type",
        "manifest",
        "ecosystem",
        "name",
        "version",
        "package_url",
    ):
        if not isinstance(row[field], str):
            raise ValueError("dependency row has an invalid required string field")
    if row["change_type"] not in {"added", "removed"}:
        raise ValueError("dependency row has an unknown change_type")
    if row["license"] is not None and not isinstance(row["license"], str):
        raise ValueError("dependency row has an invalid license field")
    if row["source_repository_url"] is not None and not isinstance(
        row["source_repository_url"], str
    ):
        raise ValueError("dependency row has an invalid source_repository_url field")
    if "scope" in row and row["scope"] not in {
        "unknown",
        "runtime",
        "development",
    }:
        raise ValueError("dependency row has an invalid scope")
    if "vulnerabilities" in row and not isinstance(row["vulnerabilities"], list):
        raise ValueError("dependency row has an invalid vulnerabilities field")
    return tuple(row[field] for field in FIELDS)


def _target_package_url(package_url: str) -> bool:
    """Match target PURLs by canonical type/name, ignoring version and qualifiers."""
    if not package_url.lower().startswith("pkg:"):
        return False
    purl_path = package_url[4:].split("?", 1)[0].split("#", 1)[0]
    package_type, separator, name_and_version = purl_path.partition("/")
    if not separator:
        return False
    raw_name = name_and_version.split("@", 1)[0]
    try:
        canonical_type = unquote(package_type, errors="strict").lower()
        canonical_name = unquote(raw_name, errors="strict")
    except UnicodeDecodeError:
        return False
    return canonical_type == TARGET_PURL_TYPE and canonical_name in TARGET_NAMES


def verify_dependency_changes(
    payload: str | list[dict[str, Any]] | None,
    required_rows: set[tuple[str, ...]] | None = None,
) -> int:
    if payload is None or payload == "":
        raise ValueError("Dependency Review dependency-changes output is missing")
    if isinstance(payload, str):
        try:
            rows = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Dependency Review dependency-changes output is invalid JSON"
            ) from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError(
            "Dependency Review dependency-changes output must be a JSON array"
        )

    accepted: Counter[tuple[str, ...]] = Counter()
    for raw_row in rows:
        identity = _action_row(raw_row)
        change_type, _manifest, _ecosystem, name, _version, _purl, license_id = identity
        if change_type == "removed":
            continue
        if (
            name not in TARGET_NAMES
            and license_id != LICENSE_REF
            and not _target_package_url(identity[5])
        ):
            continue
        if identity not in EXPECTED_ROWS:
            raise ValueError(
                "unexpected package/version/manifest/license/PURL identity"
            )
        accepted[identity] += 1
        if accepted[identity] > 1:
            raise ValueError("duplicate exact dependency exception identity")

    if (required_rows or set()) - set(accepted):
        raise ValueError(
            "Dependency Review output omitted a changed reviewed dependency row"
        )
    return sum(accepted.values())


def _reject_nonstandard_json_constant(_value: str) -> None:
    raise ValueError("non-standard JSON constant")


class _DependencyResponse:
    def __init__(self, response: Any):
        self._response = response
        self.status = getattr(response, "status", getattr(response, "code", None))
        self.headers = response.headers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def close(self) -> None:
        self._response.close()

    def geturl(self) -> str:
        return self._response.geturl()

    def read(self, limit: int = -1) -> bytes:
        return self._response.read(limit)


class _DependencyHTTPStatusError(ValueError):
    def __init__(self, status_code: int, retry_after: str | None):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"Dependency graph compare returned HTTP {status_code}")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _build_dependency_opener():
    context = ssl.create_default_context()
    context.set_alpn_protocols(["http/1.1"])
    return build_opener(
        ProxyHandler({}),
        HTTPSHandler(context=context),
        _NoRedirect(),
    )


def _dependency_request_target(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(
            "dependency compare request must use the fixed GitHub API host"
        )
    valid_owner_path = bool(
        re.fullmatch(
            r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/dependency-graph/compare/"
            r"[0-9a-f]{40}\.\.\.[0-9a-f]{40}",
            parsed.path,
        )
    )
    valid_repository_id_path = bool(
        re.fullmatch(
            r"/repositories/[0-9]+/dependency-graph/compare/"
            r"[0-9a-f]{40}\.\.\.[0-9a-f]{40}",
            parsed.path,
        )
    )
    if not (valid_owner_path or valid_repository_id_path):
        raise ValueError("dependency compare request path is invalid")
    try:
        query = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True)
    except ValueError as error:
        raise ValueError("dependency compare request query is invalid") from error
    if set(query) not in ({"per_page"}, {"page", "per_page"}):
        raise ValueError("dependency compare request query is invalid")
    if query.get("per_page") != [str(DEPENDENCY_COMPARE_PAGE_SIZE)]:
        raise ValueError("dependency compare request page size is invalid")
    if "page" in query and (
        len(query["page"]) != 1 or not re.fullmatch(r"[1-9][0-9]*", query["page"][0])
    ):
        raise ValueError("dependency compare request page is invalid")
    return parsed.path + "?" + parsed.query


def _open_dependency_request(url: str, headers: dict[str, str]) -> _DependencyResponse:
    request_target = _dependency_request_target(url)
    request_url = f"https://api.github.com{request_target}"
    opener = _build_dependency_opener()
    opener.addheaders = list(headers.items())
    try:
        response = opener.open(request_url, timeout=30)
    except HTTPError as error:
        status = error.code
        retry_after = error.headers.get("Retry-After") if error.headers else None
        error.close()
        raise _DependencyHTTPStatusError(status, retry_after) from None
    return _DependencyResponse(response)


def _bounded_retry_after_seconds(value: str | None) -> float | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not re.fullmatch(r"[0-9]{1,6}", normalized):
        return None
    return min(float(int(normalized)), DEPENDENCY_COMPARE_MAX_RETRY_AFTER_SECONDS)


def _dependency_retry_delay(attempt: int, retry_after: str | None = None) -> float:
    retry_after_seconds = _bounded_retry_after_seconds(retry_after)
    if retry_after_seconds is not None:
        return retry_after_seconds
    return min(
        DEPENDENCY_COMPARE_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
        DEPENDENCY_COMPARE_MAX_BACKOFF_SECONDS,
    )


def _is_retryable_dependency_transport_error(error: BaseException) -> bool:
    if isinstance(error, URLError):
        error = error.reason
    return isinstance(error, (ConnectionError, TimeoutError))


def _open_dependency_request_with_retries(
    url: str, headers: dict[str, str]
) -> _DependencyResponse:
    for attempt in range(1, DEPENDENCY_COMPARE_MAX_ATTEMPTS + 1):
        try:
            return _open_dependency_request(url, headers)
        except _DependencyHTTPStatusError as error:
            if (
                error.status_code not in DEPENDENCY_COMPARE_RETRY_STATUSES
                or attempt == DEPENDENCY_COMPARE_MAX_ATTEMPTS
            ):
                raise
            delay = _dependency_retry_delay(attempt, error.retry_after)
        except (URLError, OSError) as error:
            if (
                not _is_retryable_dependency_transport_error(error)
                or attempt == DEPENDENCY_COMPARE_MAX_ATTEMPTS
            ):
                raise ValueError("Dependency graph compare request failed") from None
            delay = _dependency_retry_delay(attempt)
        time.sleep(delay)
    raise ValueError("Dependency graph compare request failed")


def _next_compare_url(
    link_header: str | None,
    *,
    repository: str,
    base_sha: str,
    head_sha: str,
    current_page: int,
) -> str | None:
    if not link_header:
        return None
    ref_segment = f"{base_sha}...{head_sha}"
    next_url = None
    for part in link_header.split(","):
        match = re.fullmatch(r"\s*<([^<>]+)>\s*;\s*(.*?)\s*", part)
        if not match:
            raise ValueError("dependency compare returned an invalid pagination link")
        attributes = match.group(2)
        if not re.search(r'(?:^|;)\s*rel="?next"?(?:;|$)', attributes):
            continue
        if next_url is not None:
            raise ValueError("dependency compare returned duplicate next links")
        next_url = match.group(1)
    if next_url is None:
        return None

    parsed = urlsplit(next_url)
    valid_owner_path = (
        parsed.path == f"/repos/{repository}/dependency-graph/compare/{ref_segment}"
    )
    valid_repository_id_path = bool(
        re.fullmatch(
            rf"/repositories/[0-9]+/dependency-graph/compare/{re.escape(ref_segment)}",
            parsed.path,
        )
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not (valid_owner_path or valid_repository_id_path)
    ):
        raise ValueError("dependency compare returned an unexpected pagination URL")
    try:
        query = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True)
    except ValueError as error:
        raise ValueError(
            "dependency compare returned an invalid pagination query"
        ) from error
    if set(query) != {"page", "per_page"} or query.get("per_page") != [
        str(DEPENDENCY_COMPARE_PAGE_SIZE)
    ]:
        raise ValueError("dependency compare returned an unexpected pagination query")
    page_values = query.get("page", [])
    if len(page_values) != 1 or not page_values[0].isdigit():
        raise ValueError("dependency compare returned an invalid page number")
    next_page = int(page_values[0])
    if next_page != current_page + 1 or next_page > MAX_DEPENDENCY_COMPARE_PAGES:
        raise ValueError("dependency compare pagination is not sequential")
    return next_url


def fetch_dependency_comparison(
    repository: str, base_sha: str, head_sha: str, token: str
) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("GITHUB_REPOSITORY is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        raise ValueError("BASE_SHA must be an immutable 40-character commit SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise ValueError("HEAD_SHA must be an immutable 40-character commit SHA")
    if not token or "\n" in token or "\r" in token:
        raise ValueError("GitHub token is missing or malformed")

    url = (
        f"https://api.github.com/repos/{repository}/dependency-graph/compare/"
        f"{base_sha}...{head_sha}?per_page={DEPENDENCY_COMPARE_PAGE_SIZE}"
    )
    current_page = 1
    seen_urls: set[str] = set()
    changes: list[dict[str, Any]] = []
    total_bytes = 0
    while True:
        if url in seen_urls or current_page > MAX_DEPENDENCY_COMPARE_PAGES:
            raise ValueError(
                "dependency compare pagination repeated or exceeded its bound"
            )
        seen_urls.add(url)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "university-ecosystem-dependency-scope-guard",
        }
        try:
            response = _open_dependency_request_with_retries(url, headers)
        except (URLError, OSError):
            raise ValueError("Dependency graph compare request failed") from None

        with response:
            if response.status != 200:
                raise ValueError(
                    f"Dependency graph compare returned HTTP {response.status}"
                )
            if response.geturl() != url:
                raise ValueError(
                    "Dependency graph compare returned an unexpected response"
                )
            body = response.read(MAX_DEPENDENCY_COMPARE_BYTES - total_bytes + 1)
            link_header = response.headers.get("Link")
        total_bytes += len(body)
        if total_bytes > MAX_DEPENDENCY_COMPARE_BYTES:
            raise ValueError("Dependency graph comparison exceeds the bounded size")
        try:
            page = json.loads(
                body.decode("utf-8"), parse_constant=_reject_nonstandard_json_constant
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(
                "Dependency graph compare returned invalid JSON"
            ) from error
        if not isinstance(page, list):
            raise ValueError("Dependency graph compare response must be a JSON array")
        for row in page:
            _action_row(row)
        changes.extend(page)

        next_url = _next_compare_url(
            link_header,
            repository=repository,
            base_sha=base_sha,
            head_sha=head_sha,
            current_page=current_page,
        )
        if next_url is None:
            return changes
        url = next_url
        current_page += 1


def write_dependency_changes_file(
    changes: list[dict[str, Any]], runner_temp: Path | str
) -> tuple[Path, int]:
    directory = Path(runner_temp)
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError("RUNNER_TEMP is missing or is not an absolute directory")
    output = directory / DEPENDENCY_COMPARE_OUTPUT_NAME
    encoded = json.dumps(
        changes, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(encoded) > MAX_DEPENDENCY_COMPARE_BYTES:
        raise ValueError("Dependency graph comparison exceeds the bounded size")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(output, flags, 0o600)
    except FileExistsError as error:
        raise ValueError("Dependency comparison output file already exists") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output, len(encoded)


def read_dependency_changes_file(path: Path | str) -> list[dict[str, Any]]:
    source = Path(path)
    try:
        metadata = source.lstat()
    except OSError as error:
        raise ValueError(
            "Dependency comparison file is missing or unreadable"
        ) from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > MAX_DEPENDENCY_COMPARE_BYTES
    ):
        raise ValueError("Dependency comparison file is not a bounded regular file")
    try:
        encoded = source.read_bytes()
        if len(encoded) > MAX_DEPENDENCY_COMPARE_BYTES:
            raise ValueError("Dependency comparison file exceeds the bounded size")
        payload = json.loads(
            encoded.decode("utf-8"), parse_constant=_reject_nonstandard_json_constant
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("Dependency comparison file is invalid JSON") from error
    if not isinstance(payload, list):
        raise ValueError("Dependency comparison file must contain a JSON array")
    for row in payload:
        _action_row(row)
    return payload


def _go_requirements(text: str, wanted: set[str]) -> dict[str, list[str]]:
    found = {name: [] for name in wanted}
    in_block = False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if line == "require (":
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if line.startswith("require "):
            line = line[len("require ") :].strip()
        elif not in_block:
            continue
        match = re.match(r"^([^\s]+)\s+(v[^\s]+)(?:\s|$)", line)
        if match and match.group(1) in found:
            found[match.group(1)].append(match.group(2))
    return found


def _go_mod_tokens(line: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(line):
        char = line[index]
        if char.isspace():
            index += 1
            continue
        if line.startswith("//", index):
            break
        if line.startswith("=>", index):
            tokens.append("=>")
            index += 2
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char in ('"', "`"):
            quote = char
            start = index
            index += 1
            escaped = False
            while index < len(line):
                current = line[index]
                if quote == '"' and current == '"' and not escaped:
                    index += 1
                    break
                if quote == "`" and current == "`":
                    index += 1
                    break
                if quote == '"' and current == "\\" and not escaped:
                    escaped = True
                else:
                    escaped = False
                index += 1
            else:
                raise ValueError("unterminated quoted token in Go module file")
            raw = line[start:index]
            try:
                if quote == '"':
                    import ast

                    value = ast.literal_eval(raw)
                else:
                    value = raw[1:-1]
            except (SyntaxError, ValueError) as error:
                raise ValueError("invalid quoted token in Go module file") from error
            if not isinstance(value, str):
                raise ValueError("invalid quoted token in Go module file")
            tokens.append(value)
            continue
        start = index
        while (
            index < len(line)
            and not line[index].isspace()
            and line[index] not in '()"`'
        ):
            if line.startswith("//", index) or line.startswith("=>", index):
                break
            index += 1
        if start == index:
            raise ValueError("cannot tokenize Go module directive")
        tokens.append(line[start:index])
    return tokens


def _valid_replace_entry(tokens: list[str]) -> str:
    arrows = [index for index, lexeme in enumerate(tokens) if lexeme == "=>"]
    if len(arrows) != 1:
        raise ValueError("cannot parse Go replace directive")
    arrow = arrows[0]
    left = tokens[:arrow]
    right = tokens[arrow + 1 :]
    if len(left) not in (1, 2) or len(right) not in (1, 2):
        raise ValueError("cannot parse Go replace directive")
    if any(lexeme in "()" for lexeme in tokens) or any(
        not lexeme or any(char.isspace() for char in lexeme) for lexeme in tokens
    ):
        raise ValueError("cannot parse Go replace directive")
    # A local replacement cannot carry a new module version. Any optional
    # version token must have Go module-version shape rather than being
    # silently accepted as an unparsed extra argument.
    version_pattern = re.compile(
        r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
    )
    for version in left[1:] + right[1:]:
        if not version_pattern.fullmatch(version):
            raise ValueError("cannot parse Go replace directive")
    right_path = right[0]
    windows_absolute = bool(re.match(r"^[A-Za-z]:[\\/]", right_path))
    if (right_path.startswith((".", "/", "\\\\")) or windows_absolute) and len(
        right
    ) != 1:
        raise ValueError("cannot parse Go replace directive")
    return left[0]


def _has_tracked_replace(text: str, wanted: set[str]) -> bool:
    in_block = False
    found = False
    for raw in text.splitlines():
        tokens = _go_mod_tokens(raw)
        if not tokens:
            continue
        if not in_block and tokens[0] == "replace":
            payload = tokens[1:]
            if payload[:1] == ["("]:
                if len(payload) != 1:
                    raise ValueError("cannot parse Go replace block")
                in_block = True
                continue
            if payload and payload[0] == "(":
                raise ValueError("cannot parse Go replace block")
            if not payload:
                raise ValueError("cannot parse Go replace directive")
            if _valid_replace_entry(payload) in wanted:
                found = True
            continue
        if in_block:
            if tokens == [")"]:
                in_block = False
                continue
            if tokens[0] == "replace":
                raise ValueError("nested Go replace directive")
            if _valid_replace_entry(tokens) in wanted:
                found = True
    if in_block:
        raise ValueError("unterminated Go replace block")
    return found


def verify_current_pins(root: Path) -> dict[tuple[str, str], str]:
    current = {}
    tracked_modules = {
        module for modules in EXPECTED_MODULES.values() for module in modules
    }
    workspace = root / "go.work"
    if workspace.is_file() and _has_tracked_replace(
        workspace.read_text(encoding="utf-8"), tracked_modules
    ):
        raise ValueError("go.work replaces a tracked license-exception module")
    for manifest, expected in EXPECTED_MODULES.items():
        path = root / manifest
        if not path.is_file():
            raise ValueError(f"required module manifest is missing: {manifest}")
        text = path.read_text(encoding="utf-8")
        if _has_tracked_replace(text, set(expected)):
            raise ValueError(f"{manifest} replaces a tracked license-exception module")
        found = _go_requirements(text, set(expected))
        for module, version in expected.items():
            if found[module] != [version]:
                raise ValueError(f"{manifest} must pin {module} exactly to {version}")
            current[(manifest, module)] = version
    return current


def _git_show(root: Path, ref: str, path: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", ref) or path not in {
        CONFIG_PATH,
        *EXPECTED_MODULES,
    }:
        raise ValueError(
            "protected-base read requires an immutable SHA and known manifest"
        )
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ValueError("Git executable is unavailable")
    result = subprocess.run(  # noqa: S603 - resolved Git, validated SHA and fixed manifest paths; no shell.
        [git_executable, "show", f"{ref}:{path}"],
        cwd=root,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(f"cannot read protected-base file: {path}")
    return result.stdout.decode("utf-8")


def expected_rows_for_delta(
    base: dict[tuple[str, str], str | None],
    current: dict[tuple[str, str], str],
) -> set[tuple[str, ...]]:
    row_by_key = {(row[1], row[3]): row for row in EXPECTED_ROWS}
    return {
        row_by_key[key] for key, version in current.items() if base.get(key) != version
    }


def _base_pins(root: Path, base_sha: str) -> dict[tuple[str, str], str | None]:
    base = {}
    for manifest, expected in EXPECTED_MODULES.items():
        text = _git_show(root, base_sha, manifest)
        if _has_tracked_replace(text, set(expected)):
            raise ValueError(f"protected base replaces a tracked module in {manifest}")
        found = _go_requirements(text, set(expected))
        for module in expected:
            if len(found[module]) > 1:
                raise ValueError(
                    f"protected base has duplicate requirements in {manifest}"
                )
            base[(manifest, module)] = found[module][0] if found[module] else None
    return base


def _parse_config(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    scalars: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    active = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if raw[:1].isspace():
            if active is not None and line.startswith("- "):
                value = line[2:].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                sections[active].append(value)
            continue
        if ":" not in raw:
            raise ValueError("unrecognized dependency review YAML line")
        key, value = raw.split(":", 1)
        key, value = key.strip(), value.strip()
        active = None
        if value:
            scalars[key] = value
        else:
            sections[key] = []
            active = key
    return scalars, sections


def verify_policy_scope(current_text: str) -> None:
    scalars, sections = _parse_config(current_text)
    if (
        scalars.get("license-check") != "true"
        or scalars.get("vulnerability-check") != "true"
    ):
        raise ValueError("license-check and vulnerability-check must remain enabled")
    if LICENSE_REF in sections.get("allow-licenses", []):
        raise ValueError(
            "the unresolved OpenTelemetry marker must not enter global allow-licenses"
        )
    purls = Counter(sections.get("allow-dependencies-licenses", []))
    for purl, count in PURL_ADDITIONS.items():
        if purls[purl] != count:
            raise ValueError("an exact package-name PURL is missing or duplicated")
    for name in TARGET_NAMES:
        if any(item.startswith(f"pkg:golang/{name}@") for item in purls):
            raise ValueError(
                "a versioned target PURL cannot define the version boundary"
            )


def verify_policy_delta(base_text: str, current_text: str) -> None:
    base_scalars, base_sections = _parse_config(base_text)
    current_scalars, current_sections = _parse_config(current_text)
    if (
        current_scalars.get("license-check") != "true"
        or current_scalars.get("vulnerability-check") != "true"
    ):
        raise ValueError("license-check and vulnerability-check must remain enabled")
    if base_scalars != current_scalars:
        raise ValueError(
            "dependency review scalar policy changed outside the reviewed exception"
        )
    for key in (set(base_sections) | set(current_sections)) - {
        "allow-dependencies-licenses"
    }:
        if base_sections.get(key, []) != current_sections.get(key, []):
            raise ValueError(
                f"dependency review policy list changed unexpectedly: {key}"
            )
    old = Counter(base_sections.get("allow-dependencies-licenses", []))
    new = Counter(current_sections.get("allow-dependencies-licenses", []))
    if (new - old) - PURL_ADDITIONS:
        raise ValueError("dependency PURL additions exceed the exact reviewed set")
    for purl, count in PURL_ADDITIONS.items():
        if new[purl] != count:
            raise ValueError("an exact package-name PURL is missing or duplicated")
    if LICENSE_REF in current_sections.get("allow-licenses", []):
        raise ValueError(
            "the unresolved OpenTelemetry marker must not enter global allow-licenses"
        )


def preflight(root: Path, base_sha: str) -> set[tuple[str, ...]]:
    if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        raise ValueError("BASE_SHA must be an immutable 40-character commit SHA")
    current = verify_current_pins(root)
    current_config = (root / CONFIG_PATH).read_text(encoding="utf-8")
    verify_policy_scope(current_config)
    verify_policy_delta(_git_show(root, base_sha, CONFIG_PATH), current_config)
    return expected_rows_for_delta(_base_pins(root, base_sha), current)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("preflight", "fetch", "changes"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha")
    parser.add_argument("--changes-file", type=Path)
    args = parser.parse_args()
    required = preflight(args.root, args.base_sha)
    if args.phase == "preflight":
        print(
            "verified exact dependency license scope and current pins; "
            f"changed_target_rows={len(required)}"
        )
        return 0
    if args.phase == "fetch":
        head_sha = args.head_sha or os.environ.get("HEAD_SHA", "")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        token = os.environ.get("GITHUB_TOKEN", "")
        changes = fetch_dependency_comparison(
            repository, args.base_sha, head_sha, token
        )
        _output, byte_count = write_dependency_changes_file(
            changes, os.environ.get("RUNNER_TEMP", "")
        )
        print(
            "saved bounded Dependency Review comparison; "
            f"rows={len(changes)} bytes={byte_count}"
        )
        return 0
    if args.changes_file is None:
        raise ValueError("--changes-file is required for the changes phase")
    changes = read_dependency_changes_file(args.changes_file)
    accepted = verify_dependency_changes(changes, required)
    print(f"verified comparison schema and exact license rows; accepted={accepted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
