"""Bind the owner-approved DAST policy (ADR-047, 2026-11-21) to the product source.

The ZAP scan reports CSRF-token alerts on script-submitted forms as
informational, and lowers the style-src 'unsafe-inline' CSP sub-alert to low.
These checks keep both downgrades from silently widening: every native POST form
must carry the marker the scanner looks for, and every served policy must keep
the exact style-src directive the accepted-risk filter matches.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core.policies.csp import SPOTIFY_IMAGE_ORIGIN, ContentSecurityPolicy
from scripts.quality.zap_origin_evidence import ACCEPTED_STYLE_SRC_EVIDENCE
from scripts.quality.zap_runner import _CONTAINER_ENTRY

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SOURCE = ROOT / "frontend" / "src"
MARKER_MODULE = FRONTEND_SOURCE / "utils" / "apiSubmittedForm.ts"
NODE_CSP = ROOT / "frontend" / "scripts" / "server-csp.mjs"
FORM_TAG = re.compile(r"<form\b(?P<attributes>[^>]*)>", re.DOTALL)
APPROVED_STYLE_SRC = "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"
SHARED_CSP_CONTRACT = ROOT / "quality" / "frontend-csp-defaults.json"
# ZAP 10055-4 fix: no wildcard or scheme-only image source; Spotify album art is
# the only third-party image origin.
APPROVED_IMG_SRC = "img-src 'self' data: blob: https://i.scdn.co"


def _production_sources() -> list[Path]:
    return sorted(
        path
        for path in FRONTEND_SOURCE.rglob("*.tsx")
        if "__tests__" not in path.parts
        and not path.name.endswith((".test.tsx", ".stories.tsx"))
    )


def test_marker_matches_the_scanner_csrf_annotation() -> None:
    source = MARKER_MODULE.read_text(encoding="utf-8")
    assert 'export const API_SUBMITTED_FORM = { "data-csrf": "header" } as const' in (
        source
    )
    assert "-config rules.csrf.ignore.attname=data-csrf" in _CONTAINER_ENTRY
    assert "-config rules.csrf.ignore.attvalue=header" in _CONTAINER_ENTRY


def test_every_native_post_form_is_marked_as_api_submitted() -> None:
    marked = []
    for path in _production_sources():
        for match in FORM_TAG.finditer(path.read_text(encoding="utf-8")):
            attributes = match.group("attributes")
            if 'method="post"' not in attributes:
                continue
            assert "{...API_SUBMITTED_FORM}" in attributes, path
            marked.append(path.relative_to(FRONTEND_SOURCE).as_posix())
    assert marked == [
        "components/auth/LoginCredentialForm.tsx",
        "pages/Register.tsx",
        "pages/ResetPassword.tsx",
    ]


def _node_policy_directive() -> str:
    directives = re.findall(
        r'"(style-src [^"]+)"', NODE_CSP.read_text(encoding="utf-8")
    )
    assert len(directives) == 1
    return directives[0]


@pytest.mark.parametrize("is_development", [False, True])
def test_backend_policy_keeps_the_accepted_style_src(is_development: bool) -> None:
    header = ContentSecurityPolicy(is_development=is_development).generate(
        nonce="bm9uY2U="
    )
    assert re.fullmatch(ACCEPTED_STYLE_SRC_EVIDENCE, header)


def test_node_policy_keeps_the_accepted_style_src() -> None:
    directive = _node_policy_directive()
    assert directive == APPROVED_STYLE_SRC
    header = f"default-src 'self'; {directive}; img-src 'self'"
    assert re.fullmatch(ACCEPTED_STYLE_SRC_EVIDENCE, header)


@pytest.mark.parametrize(
    "directive",
    [
        f"{APPROVED_STYLE_SRC} https:",
        f"{APPROVED_STYLE_SRC} 'unsafe-eval'",
        f"{APPROVED_STYLE_SRC}.attacker.invalid",
        "style-src 'self' 'unsafe-inline' *",
        "style-src * 'unsafe-inline' https://fonts.googleapis.com",
    ],
)
def test_accepted_filter_does_not_cover_a_wider_style_src(directive: str) -> None:
    header = f"default-src 'self'; {directive}; img-src 'self'"
    assert re.fullmatch(ACCEPTED_STYLE_SRC_EVIDENCE, header) is None


@pytest.mark.parametrize(
    "header",
    [
        APPROVED_STYLE_SRC,
        f"default-src 'self'; {APPROVED_STYLE_SRC}; img-src 'self'",
        f"{APPROVED_STYLE_SRC}; style-src-elem 'self'",
        f"default-src https://example.invalid/style-src; {APPROVED_STYLE_SRC}",
        f"default-src 'self'; DEFAULT-SRC *; {APPROVED_STYLE_SRC}",
    ],
)
def test_accepted_filter_matches_one_complete_policy(header: str) -> None:
    assert re.fullmatch(ACCEPTED_STYLE_SRC_EVIDENCE, header)
    assert re.search(ACCEPTED_STYLE_SRC_EVIDENCE, header)


def test_accepted_filter_matches_shared_policy_headers() -> None:
    shared = json.loads(SHARED_CSP_CONTRACT.read_text(encoding="utf-8"))
    for header in shared["headers"].values():
        assert re.fullmatch(ACCEPTED_STYLE_SRC_EVIDENCE, header)
        assert re.search(ACCEPTED_STYLE_SRC_EVIDENCE, header)


@pytest.mark.parametrize(
    "header",
    [
        "style-src-elem 'unsafe-inline'",
        f"style-src 'self' 'unsafe-inline' *; {APPROVED_STYLE_SRC}",
        f"Style-Src 'self' 'unsafe-inline' *; {APPROVED_STYLE_SRC}",
        f"{APPROVED_STYLE_SRC}; STYLE-SRC 'self' 'unsafe-inline' *",
        f"{APPROVED_STYLE_SRC}; {APPROVED_STYLE_SRC}",
        f"{APPROVED_STYLE_SRC}; default-src 'self', style-src *",
        f"default-src 'self', style-src *; {APPROVED_STYLE_SRC}",
        f"style-src *\r\n{APPROVED_STYLE_SRC}",
        f"{APPROVED_STYLE_SRC}\nstyle-src *",
        f"{APPROVED_STYLE_SRC}\r",
        f"prefix-{APPROVED_STYLE_SRC}",
        f"{APPROVED_STYLE_SRC} suffix",
        f"{APPROVED_STYLE_SRC}; =malformed",
        f"{APPROVED_STYLE_SRC}; ; img-src 'self'",
        f"{APPROVED_STYLE_SRC}; img-src 'self'\x00",
    ],
)
def test_accepted_filter_rejects_ambiguous_policy_evidence(header: str) -> None:
    assert re.fullmatch(ACCEPTED_STYLE_SRC_EVIDENCE, header) is None
    assert re.search(ACCEPTED_STYLE_SRC_EVIDENCE, header) is None


def _img_src_directives(header: str) -> list[str]:
    return [
        directive.strip()
        for directive in header.split(";")
        if directive.strip().startswith("img-src")
    ]


@pytest.mark.parametrize("is_development", [False, True])
def test_backend_img_src_lists_only_the_spotify_image_origin(
    is_development: bool,
) -> None:
    assert SPOTIFY_IMAGE_ORIGIN == "https://i.scdn.co"
    header = ContentSecurityPolicy(is_development=is_development).generate(
        nonce="bm9uY2U="
    )
    assert _img_src_directives(header) == [APPROVED_IMG_SRC]


def test_node_and_shared_policies_list_only_the_spotify_image_origin() -> None:
    node = re.findall(r'"(img-src [^"]+)"', NODE_CSP.read_text(encoding="utf-8"))
    assert node == [APPROVED_IMG_SRC]
    shared = json.loads(SHARED_CSP_CONTRACT.read_text(encoding="utf-8"))
    headers = list(shared["headers"].values())
    assert len(headers) == 2
    for header in headers:
        assert _img_src_directives(header) == [APPROVED_IMG_SRC]
