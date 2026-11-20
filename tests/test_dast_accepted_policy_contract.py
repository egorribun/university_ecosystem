"""Bind the owner-approved DAST policy (ADR-047, 2026-11-21) to the product source.

The ZAP scan reports CSRF-token alerts on script-submitted forms as
informational, and lowers the style-src 'unsafe-inline' CSP sub-alert to low.
These checks keep both downgrades from silently widening: every native POST form
must carry the marker the scanner looks for, and every served policy must keep
the exact style-src directive the accepted-risk filter matches.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.policies.csp import ContentSecurityPolicy
from scripts.quality.zap_origin_evidence import ACCEPTED_STYLE_SRC_EVIDENCE
from scripts.quality.zap_runner import _CONTAINER_ENTRY

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SOURCE = ROOT / "frontend" / "src"
MARKER_MODULE = FRONTEND_SOURCE / "utils" / "apiSubmittedForm.ts"
NODE_CSP = ROOT / "frontend" / "scripts" / "server-csp.mjs"
FORM_TAG = re.compile(r"<form\b(?P<attributes>[^>]*)>", re.DOTALL)
APPROVED_STYLE_SRC = "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"


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
