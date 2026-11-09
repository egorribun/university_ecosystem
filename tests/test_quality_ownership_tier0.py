from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP_PATH = ROOT / "quality" / "ownership-mapping.json"

ORIGINAL_TIER0_RULES = (
    "**/auth/**",
    "**/session/**",
    "**/sessions/**",
    "**/security/**",
    "**/ratelimit/**",
    "**/pii/**",
    "**/migration/**",
    "**/migrations/**",
    "**/cryptography/**",
    "**/crypto/**",
    "**/spicedb/**",
    "**/rebac/**",
    "**/csrf/**",
    "**/mfa/**",
    "**/ticketing/**",
    "alembic/versions/**",
    "app/core/feature_flags.py",
    "native/rust_ext/**",
    "frontend/rust-crypto/**",
    "frontend/wasm-sanitizer/**",
)

# Security and authentication modules whose names, not directories, identify
# them.  Each must match an explicit Tier 0 rule.
SECURITY_MODULES_OUTSIDE_DIRECTORY_RULES = (
    "app/services/audit_service.py",
    "app/services/auth_service.py",
    "app/core/csrf.py",
    "app/core/ssrf.py",
    "app/core/security_headers.py",
    "app/core/config/security.py",
    "app/core/config/mixins/jwt_settings.py",
    "app/core/spicedb.py",
    "app/api/ws/authenticator.py",
    "app/api/sessions.py",
    "app/services/mfa_challenge_cleanup.py",
    "app/services/session_service.py",
    "app/utils/encryption.py",
    "services/gateway/middleware/auth.go",
    "services/gateway/middleware/ratelimit.go",
    "services/ws-hub/pkg/hub/session_ws.go",
    "services/ws-hub/pkg/config/secret_open_unix.go",
    "frontend/src/contexts/AuthContext.tsx",
    "frontend/src/app/sessionMutationCache.ts",
    "frontend/src/api/mfa.ts",
)

NON_SECURITY_MODULES = (
    "app/services/news_service.py",
    "app/services/event_service.py",
    "frontend/src/components/news/NewsCard.tsx",
)


@pytest.fixture
def normalizer(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts" / "quality"))
    return importlib.import_module("normalize_coverage_reports")


@pytest.fixture
def tier0_rules() -> list[str]:
    document = json.loads(OWNERSHIP_PATH.read_text(encoding="utf-8"))
    return list(document["tier0_rules"])


def _is_tier0(normalizer: ModuleType, path: str, rules: list[str]) -> bool:
    return any(normalizer._tier0_rule_matches(path, rule) for rule in rules)


def test_security_modules_named_outside_directory_rules_are_tier0(
    normalizer: ModuleType,
    tier0_rules: list[str],
) -> None:
    missed = [
        path
        for path in SECURITY_MODULES_OUTSIDE_DIRECTORY_RULES
        if not _is_tier0(normalizer, path, tier0_rules)
    ]

    assert missed == []


def test_tightened_mapping_preserves_every_original_tier0_rule(
    tier0_rules: list[str],
) -> None:
    assert set(ORIGINAL_TIER0_RULES) <= set(tier0_rules)


def test_directory_rules_still_cover_security_packages(
    normalizer: ModuleType,
    tier0_rules: list[str],
) -> None:
    assert _is_tier0(normalizer, "app/services/auth/login_service.py", tier0_rules)
    assert _is_tier0(normalizer, "app/core/ratelimit/logic.py", tier0_rules)


def test_non_security_modules_are_not_pulled_into_tier0(
    normalizer: ModuleType,
    tier0_rules: list[str],
) -> None:
    matched = [
        path
        for path in NON_SECURITY_MODULES
        if _is_tier0(normalizer, path, tier0_rules)
    ]

    assert matched == []
