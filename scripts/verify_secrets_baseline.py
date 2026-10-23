#!/usr/bin/env python3
"""Fail-closed verification for a detect-secrets baseline.

The committed baseline is an allowlist of individual findings, not merely a
list of files.  A fresh scan must therefore be a subset of the baseline (old
entries are allowed to become stale when a secret is removed), while a pull
request must not add a new suppression relative to a trusted base baseline.

An owner-authored policy update may opt into exact-identity dispositions only
when the protected workflow explicitly confirms the author and candidate change.
Other pull requests use the trusted base and ignore candidate policy additions.

Usage::

    python scripts/verify_secrets_baseline.py BASELINE CURRENT_SCAN
    python scripts/verify_secrets_baseline.py BASELINE CURRENT_SCAN \
        --trusted-base-baseline TRUSTED_BASELINE \
        --trusted-base-source-sha BASE_SHA

Exit code 0 means no unsuppressed findings were detected.  Exit code 1 means
the current scan found a finding that is not in the committed baseline, or a
pull request added a suppression for a finding relative to its trusted base, or
the source delta added an inline secret-allowlist pragma. The source check
runs when --trusted-base-source-sha is supplied. Exit code 2 means an
artifact or trusted source delta is missing or malformed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any


class BaselineArtifactError(ValueError):
    """Raised when a baseline or scan artifact cannot be trusted."""


class SourceDeltaError(ValueError):
    """Raised when a trusted source delta cannot be verified safely."""


_SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_INLINE_SECRET_ALLOWLIST_PATTERN = re.compile(
    r"\bpragma\s*:\s*allowlist\s+secret\b", re.IGNORECASE
)
_DIFF_HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_FALSE_POSITIVE_ALLOWED_TYPE = "Hex High Entropy String"
_FALSE_POSITIVE_HEX_CATEGORIES = frozenset(
    {
        "public_integrity_digest",
        "documented_crypto_test_vector",
        "independent_contract_fingerprint",
    }
)
_FALSE_POSITIVE_NON_HEX_CATEGORY_PATH_TYPES = {
    "ci_test_contract_sentinel": frozenset(
        {
            (".github/workflows/ci.yml", "Basic Auth Credentials"),
            (".github/workflows/ci.yml", "Secret Keyword"),
            (".github/workflows/nightly-full-gate.yml", "Secret Keyword"),
            (
                "frontend/scripts/frontend-quality-contract.test.mjs",
                "Secret Keyword",
            ),
            (
                "frontend/src/api/hooks/__tests__/campusConfig.test.ts",
                "Secret Keyword",
            ),
            (
                "tests/test_live_stand_resource_guard.py",
                "Base64 High Entropy String",
            ),
            (
                "tests/test_start_docker_orphan_ownership.py",
                "Base64 High Entropy String",
            ),
            (
                "services/gateway/internal/config/secret_files_test.go",
                "Secret Keyword",
            ),
            (
                "services/ws-hub/pkg/config/secret_files_test.go",
                "Secret Keyword",
            ),
        }
    ),
    "public_package_integrity_metadata": frozenset(
        {
            (
                "frontend/scripts/stryker-inventory.test.mjs",
                "Base64 High Entropy String",
            ),
            (
                "frontend/scripts/generate-activity-pdf-font.py",
                "Base64 High Entropy String",
            ),
            (
                "frontend/src/assets/fonts/inter-latin-cyrillic-400.provenance.json",
                "Base64 High Entropy String",
            ),
        }
    ),
    "public_totp_algorithm_alphabet": frozenset(
        {
            (
                "frontend/tests/e2e-live/totp-recovery.live.spec.ts",
                "Base64 High Entropy String",
            ),
        }
    ),
    "documented_dummy_password_hash": frozenset(
        {
            ("app/auth/security.py", "Secret Keyword"),
            ("tests/test_seed_admin_data.py", "Secret Keyword"),
            (
                "tests/test_seed_demo_account_preservation.py",
                "Secret Keyword",
            ),
            ("tests/test_seed_demo_messenger.py", "Secret Keyword"),
        }
    ),
    "synthetic_hmac_test_material": frozenset(
        {
            (
                "services/gateway/internal/handlers/handlers_identity_closure_test.go",
                "Secret Keyword",
            ),
            (
                "services/ws-hub/pkg/hub/replay_security_adversarial_test.go",
                "Secret Keyword",
            ),
            (
                "tests/integration/test_historical_attendance_sender_migrations_postgres.py",
                "Secret Keyword",
            ),
        }
    ),
    "synthetic_fakeredis_lease_token": frozenset(
        {
            ("tests/test_chat_command_failure_paths.py", "Secret Keyword"),
        }
    ),
    "domain_resource_contract_fixture": frozenset(
        {
            ("tests/test_live_stand_resource_guard.py", "Secret Keyword"),
        }
    ),
    "internal_demo_stand_account_fixture": frozenset(
        {
            ("frontend/tests/e2e-live/fixtures.ts", "Secret Keyword"),
        }
    ),
}
_FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS = {
    "synthetic_achievement_url_test_fixture": (
        "synthetic profile achievement URL test fixture",
        "reserved example.test host",
        "embedded-auth rejection coverage",
        "not credential material",
    ),
    "public_compose_inspection_test_sentinel": (
        "public Compose inspection test sentinel",
        "live-stand-inspection-placeholder",
        "LIVE_VAPID_PRIVATE_KEY",
        "no-I/O request expectation",
        "not credential material",
    ),
    "internal_demo_stand_account_fixture": (
        "docs/superpowers/plans/MVP_MASTER_PLAN.md:37",
        "external operational status remains unverified",
    ),
    "external_kubernetes_secret_reference": (
        "Kubernetes external Secret object name or key reference",
        "not credential material",
    ),
    "source_contract_identifier": (
        "secret-related source identifier or required key-list expression",
        "not credential material",
    ),
    "auth_validation_ui_copy": (
        "English auth validation UI copy",
        "user-visible password validation messages",
        "not credential material",
    ),
    "aud253_private_env_mode_test_fixture": (
        "AUD-253 private environment-file mode test fixture",
        "not credential material",
    ),
    "aud495_cache_key_redaction_test_fixture": (
        "AUD-495 cache-key log-redaction test fixture",
        "synthetic canary used only by mocked backend tests",
        "tests assert logger output omits the canary",
        "not credential material",
    ),
}
_FALSE_POSITIVE_EXACT_IDENTITY_CATEGORIES = frozenset(
    {
        "external_kubernetes_secret_reference",
        "source_contract_identifier",
        "public_compose_inspection_test_sentinel",
        "synthetic_achievement_url_test_fixture",
        "auth_validation_ui_copy",
        "aud253_private_env_mode_test_fixture",
        "aud495_cache_key_redaction_test_fixture",
    }
)
_FALSE_POSITIVE_CATEGORIES = (
    _FALSE_POSITIVE_HEX_CATEGORIES
    | frozenset(_FALSE_POSITIVE_NON_HEX_CATEGORY_PATH_TYPES)
    | _FALSE_POSITIVE_EXACT_IDENTITY_CATEGORIES
)
_INDEPENDENT_CONTRACT_FINGERPRINT_PATH = (
    "tests/fixtures/full-backend-reusable-baseline.v3.yaml"
)
_V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES = frozenset(
    {
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(1, 40, 216, 231, 186, 168, 79, 45, 125, 132),
                *(127, 168, 5, 28, 100, 153, 174, 234, 240, 125),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(3, 6, 12, 132, 101, 74, 239, 234, 228, 202),
                *(159, 37, 40, 123, 95, 71, 56, 196, 220, 132),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(5, 191, 28, 206, 205, 239, 145, 213, 59, 134),
                *(193, 227, 48, 175, 150, 65, 120, 18, 200, 232),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(9, 108, 222, 83, 104, 106, 221, 81, 160, 219),
                *(50, 26, 239, 180, 179, 171, 151, 235, 111, 27),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(12, 251, 232, 137, 68, 1, 141, 98, 52, 149),
                *(161, 24, 104, 138, 2, 122, 220, 235, 41, 101),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(20, 250, 45, 5, 62, 157, 142, 242, 201, 143),
                *(116, 148, 212, 168, 68, 58, 144, 147, 163, 134),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(35, 213, 182, 113, 232, 209, 222, 172, 133, 28),
                *(134, 11, 66, 204, 140, 16, 73, 102, 122, 161),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(41, 121, 3, 166, 39, 210, 112, 61, 71, 188),
                *(65, 217, 178, 203, 150, 251, 245, 47, 98, 40),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(63, 139, 180, 44, 161, 216, 96, 230, 103, 86),
                *(57, 145, 230, 47, 43, 217, 165, 220, 9, 96),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(65, 216, 252, 230, 125, 210, 45, 81, 252, 175),
                *(221, 101, 4, 191, 77, 5, 150, 160, 247, 190),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(89, 177, 135, 249, 17, 202, 27, 56, 229, 110),
                *(173, 73, 93, 107, 166, 134, 249, 178, 171, 206),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(93, 11, 139, 187, 250, 105, 106, 185, 198, 172),
                *(140, 49, 200, 63, 87, 3, 177, 94, 22, 192),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(117, 178, 143, 89, 125, 38, 90, 83, 185, 36),
                *(217, 212, 183, 31, 59, 30, 105, 173, 130, 83),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(135, 208, 134, 129, 28, 82, 159, 105, 36, 63),
                *(184, 135, 8, 199, 53, 188, 85, 58, 0, 104),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(153, 222, 61, 254, 149, 254, 154, 225, 10, 207),
                *(194, 254, 233, 45, 153, 211, 60, 76, 96, 21),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(173, 28, 216, 212, 47, 98, 183, 251, 61, 52),
                *(51, 240, 112, 24, 36, 59, 168, 159, 144, 33),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(183, 180, 84, 90, 60, 190, 83, 232, 231, 18),
                *(129, 14, 19, 10, 138, 80, 189, 2, 65, 100),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(186, 158, 26, 65, 231, 126, 6, 219, 100, 35),
                *(248, 91, 82, 105, 155, 37, 12, 228, 251, 252),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(186, 204, 138, 143, 127, 191, 176, 115, 155, 12),
                *(75, 118, 149, 218, 93, 175, 71, 198, 65, 59),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(192, 69, 156, 120, 33, 227, 244, 212, 10, 179),
                *(65, 156, 81, 133, 11, 236, 169, 122, 247, 135),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(205, 28, 18, 150, 249, 138, 165, 177, 161, 148),
                *(203, 0, 31, 223, 240, 164, 141, 97, 51, 213),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(215, 253, 127, 30, 142, 220, 35, 245, 116, 191),
                *(41, 93, 80, 3, 111, 68, 40, 157, 38, 241),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(217, 207, 45, 166, 207, 159, 78, 30, 205, 7),
                *(120, 234, 142, 92, 13, 250, 201, 43, 63, 130),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(218, 173, 4, 103, 108, 233, 146, 226, 249, 242),
                *(43, 78, 158, 238, 35, 190, 233, 208, 195, 187),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(230, 148, 135, 74, 18, 68, 221, 38, 138, 210),
                *(117, 207, 84, 55, 156, 45, 86, 114, 3, 141),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(243, 225, 251, 63, 214, 118, 188, 212, 177, 171),
                *(7, 138, 236, 152, 163, 46, 221, 86, 11, 7),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                *(248, 237, 176, 97, 148, 41, 246, 135, 86, 11),
                *(12, 80, 246, 227, 80, 183, 82, 39, 146, 12),
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                85,
                158,
                8,
                17,
                13,
                217,
                219,
                104,
                145,
                111,
                194,
                19,
                60,
                251,
                92,
                240,
                212,
                85,
                113,
                116,
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                94,
                40,
                155,
                35,
                12,
                205,
                36,
                191,
                27,
                93,
                89,
                252,
                6,
                36,
                193,
                174,
                240,
                78,
                30,
                64,
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                228,
                251,
                163,
                207,
                40,
                164,
                144,
                11,
                26,
                225,
                79,
                240,
                197,
                199,
                12,
                121,
                37,
                113,
                215,
                216,
            ),
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                109,
                237,
                50,
                137,
                135,
                161,
                1,
                220,
                60,
                104,
                144,
                173,
                229,
                20,
                90,
                76,
                18,
                192,
                224,
                154,
            ),
        ),
    }
)

_EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES = frozenset(
    {
        (
            "charts/redis-compat/values.yaml",
            "Secret Keyword",
            (
                *(60, 145, 239, 110, 133, 210, 207, 97, 165, 191),
                *(119, 46, 40, 189, 29, 120, 234, 215, 186, 20),
            ),
        ),
        (
            "charts/redis-compat/values.yaml",
            "Secret Keyword",
            (
                *(230, 213, 95, 3, 24, 191, 137, 217, 55, 160),
                *(41, 107, 128, 143, 213, 245, 245, 238, 106, 7),
            ),
        ),
        (
            "charts/revocation-store/values.yaml",
            "Secret Keyword",
            (
                *(145, 79, 6, 243, 53, 160, 184, 10, 45, 6),
                *(149, 97, 154, 41, 139, 248, 40, 231, 216, 200),
            ),
        ),
        (
            "charts/revocation-store/values.yaml",
            "Secret Keyword",
            (
                *(176, 224, 33, 74, 155, 8, 223, 225, 252, 220),
                *(163, 143, 85, 240, 84, 244, 80, 236, 147, 249),
            ),
        ),
        (
            "charts/university-ecosystem/values-staging.yaml",
            "Secret Keyword",
            (
                *(243, 88, 195, 235, 27, 225, 239, 237, 144, 91),
                *(190, 23, 92, 20, 144, 235, 142, 255, 107, 8),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(83, 98, 194, 42, 247, 205, 142, 240, 15, 107),
                *(255, 91, 154, 24, 53, 136, 58, 143, 160, 152),
            ),
        ),
        (
            "tests/test_helm_staging_contract.py",
            "Secret Keyword",
            (
                *(243, 88, 195, 235, 27, 225, 239, 237, 144, 91),
                *(190, 23, 92, 20, 144, 235, 142, 255, 107, 8),
            ),
        ),
        (
            "tests/test_mfa_helm_contract.py",
            "Secret Keyword",
            (
                *(40, 1, 220, 132, 98, 247, 193, 134, 149, 131),
                *(209, 110, 28, 147, 90, 88, 196, 55, 233, 232),
            ),
        ),
        (
            "tests/test_revocation_store_security_contract.py",
            "Secret Keyword",
            (
                *(176, 224, 33, 74, 155, 8, 223, 225, 252, 220),
                *(163, 143, 85, 240, 84, 244, 80, 236, 147, 249),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(215, 128, 41, 160, 160, 238, 139, 18, 149, 143),
                *(57, 250, 33, 249, 44, 57, 197, 39, 22, 76),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(184, 62, 251, 137, 16, 10, 95, 17, 181, 203),
                *(68, 24, 71, 19, 38, 246, 197, 182, 105, 199),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(52, 251, 196, 127, 53, 92, 254, 52, 217, 163),
                *(55, 207, 111, 219, 105, 124, 63, 251, 88, 207),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(131, 225, 127, 34, 88, 130, 141, 189, 127, 37),
                *(151, 10, 205, 130, 50, 6, 156, 134, 123, 63),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(151, 43, 250, 167, 88, 210, 244, 121, 193, 208),
                *(14, 9, 250, 28, 65, 144, 175, 230, 64, 33),
            ),
        ),
        (
            "tests/test_helm_staging_contract.py",
            "Secret Keyword",
            (
                *(228, 120, 5, 127, 253, 132, 74, 75, 130, 206),
                *(24, 51, 247, 43, 169, 169, 236, 9, 171, 180),
            ),
        ),
        (
            "tests/test_helm_staging_contract.py",
            "Secret Keyword",
            (
                *(166, 136, 165, 50, 139, 178, 237, 65, 213, 213),
                *(244, 211, 213, 54, 181, 41, 221, 204, 57, 247),
            ),
        ),
        (
            "tests/test_helm_staging_contract.py",
            "Secret Keyword",
            (
                *(184, 62, 251, 137, 16, 10, 95, 17, 181, 203),
                *(68, 24, 71, 19, 38, 246, 197, 182, 105, 199),
            ),
        ),
        (
            "tests/test_helm_staging_contract.py",
            "Secret Keyword",
            (
                *(131, 225, 127, 34, 88, 130, 141, 189, 127, 37),
                *(151, 10, 205, 130, 50, 6, 156, 134, 123, 63),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(123, 77, 125, 47, 161, 133, 114, 12, 211, 156),
                *(161, 83, 218, 176, 239, 161, 33, 63, 175, 3),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(179, 134, 199, 26, 164, 113, 251, 90, 112, 89),
                *(155, 236, 25, 205, 45, 178, 36, 177, 213, 230),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(190, 202, 178, 95, 233, 61, 128, 186, 2, 122),
                *(157, 38, 242, 0, 238, 51, 108, 85, 192, 25),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(34, 246, 11, 80, 146, 202, 185, 32, 115, 107),
                *(90, 153, 87, 25, 88, 125, 93, 83, 53, 37),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(242, 129, 184, 11, 173, 250, 216, 254, 140, 8),
                *(84, 199, 2, 71, 104, 6, 86, 104, 233, 209),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(192, 242, 88, 136, 166, 69, 203, 190, 182, 43),
                *(194, 32, 239, 105, 71, 214, 101, 100, 77, 71),
            ),
        ),
        (
            "tests/test_docker_startup_contracts.py",
            "Secret Keyword",
            (
                *(84, 89, 170, 160, 12, 140, 117, 55, 2, 255),
                *(120, 225, 28, 28, 241, 101, 210, 110, 232, 156),
            ),
        ),
        (
            "security/trivy-university-values.yaml",
            "Secret Keyword",
            (
                *(227, 206, 244, 201, 253, 191, 204, 143, 195, 74),
                *(35, 39, 210, 43, 64, 145, 65, 224, 73, 206),
            ),
        ),
        (
            "tests/test_mfa_helm_contract.py",
            "Secret Keyword",
            (
                *(123, 77, 125, 47, 161, 133, 114, 12, 211, 156),
                *(161, 83, 218, 176, 239, 161, 33, 63, 175, 3),
            ),
        ),
    }
)

_C6_CODE_FRAGMENT_IDENTITIES = frozenset(
    {
        (
            "services/file-processor/internal/config/secret_files_test.go",
            "Secret Keyword",
            (
                *(131, 100, 141, 215, 225, 114, 137, 18, 24, 198),
                *(68, 217, 118, 34, 134, 248, 239, 30, 232, 54),
            ),
        ),
        (
            "services/file-processor/internal/config/secret_open_portable.go",
            "Secret Keyword",
            (
                *(41, 227, 142, 152, 109, 115, 112, 221, 165, 52),
                *(197, 157, 192, 180, 13, 154, 187, 19, 33, 128),
            ),
        ),
        (
            "services/file-processor/internal/config/secret_open_unix.go",
            "Secret Keyword",
            (
                *(208, 64, 95, 145, 172, 71, 37, 69, 44, 96),
                *(175, 238, 205, 43, 187, 88, 238, 101, 164, 79),
            ),
        ),
        (
            "services/gateway/internal/config/secret_files_test.go",
            "Secret Keyword",
            (
                *(131, 100, 141, 215, 225, 114, 137, 18, 24, 198),
                *(68, 217, 118, 34, 134, 248, 239, 30, 232, 54),
            ),
        ),
        (
            "services/gateway/internal/config/secret_open_portable.go",
            "Secret Keyword",
            (
                *(41, 227, 142, 152, 109, 115, 112, 221, 165, 52),
                *(197, 157, 192, 180, 13, 154, 187, 19, 33, 128),
            ),
        ),
        (
            "services/gateway/internal/config/secret_open_unix.go",
            "Secret Keyword",
            (
                *(208, 64, 95, 145, 172, 71, 37, 69, 44, 96),
                *(175, 238, 205, 43, 187, 88, 238, 101, 164, 79),
            ),
        ),
        (
            "services/ws-hub/pkg/config/secret_files_test.go",
            "Secret Keyword",
            (
                *(131, 100, 141, 215, 225, 114, 137, 18, 24, 198),
                *(68, 217, 118, 34, 134, 248, 239, 30, 232, 54),
            ),
        ),
        (
            "services/ws-hub/pkg/config/secret_open_portable.go",
            "Secret Keyword",
            (
                *(41, 227, 142, 152, 109, 115, 112, 221, 165, 52),
                *(197, 157, 192, 180, 13, 154, 187, 19, 33, 128),
            ),
        ),
        (
            "services/ws-hub/pkg/config/secret_open_unix.go",
            "Secret Keyword",
            (
                *(208, 64, 95, 145, 172, 71, 37, 69, 44, 96),
                *(175, 238, 205, 43, 187, 88, 238, 101, 164, 79),
            ),
        ),
    }
)
_PAGE_TITLE_ROUTE_IDENTIFIER_IDENTITIES = frozenset(
    {
        (
            "frontend/src/components/ui/PageRouteSEO.tsx",
            "Secret Keyword",
            (
                *(246, 11, 35, 176, 57, 187, 96, 181, 93, 29),
                *(195, 205, 161, 83, 22, 254, 236, 136, 40, 118),
            ),
        ),
        (
            "frontend/src/components/ui/PageRouteSEO.tsx",
            "Secret Keyword",
            (
                *(13, 39, 13, 74, 47, 213, 87, 245, 102, 242),
                *(14, 180, 169, 34, 53, 125, 169, 142, 149, 34),
            ),
        ),
    }
)


_SOURCE_CONTRACT_IDENTIFIER_IDENTITIES = frozenset(
    {
        (
            "charts/university-ecosystem/templates/backend-deployment.yaml",
            "Secret Keyword",
            (
                *(30, 194, 182, 128, 159, 103, 156, 203, 183, 26),
                *(23, 40, 90, 62, 43, 252, 176, 15, 18, 186),
            ),
        ),
        (
            "charts/university-ecosystem/templates/backend-deployment.yaml",
            "Secret Keyword",
            (
                *(161, 100, 27, 75, 156, 55, 15, 154, 164, 170),
                *(53, 172, 62, 240, 50, 199, 46, 203, 197, 40),
            ),
        ),
        (
            "services/file-processor/internal/config/secret_files.go",
            "Secret Keyword",
            (
                *(40, 248, 41, 221, 11, 70, 108, 16, 156, 35),
                *(203, 246, 53, 249, 173, 170, 93, 83, 33, 10),
            ),
        ),
        (
            "services/file-processor/internal/config/secret_files_test.go",
            "Secret Keyword",
            (
                *(108, 70, 216, 212, 158, 167, 6, 198, 215, 191),
                *(27, 58, 194, 136, 17, 163, 55, 62, 155, 132),
            ),
        ),
        (
            "services/ws-hub/pkg/config/coverage_fail_closed_test.go",
            "Secret Keyword",
            (
                *(127, 111, 104, 190, 234, 156, 19, 213, 38, 190),
                *(1, 35, 147, 42, 52, 191, 220, 9, 48, 66),
            ),
        ),
        (
            "services/ws-hub/pkg/config/secret_files_close_test.go",
            "Secret Keyword",
            (
                *(127, 111, 104, 190, 234, 156, 19, 213, 38, 190),
                *(1, 35, 147, 42, 52, 191, 220, 9, 48, 66),
            ),
        ),
        *_C6_CODE_FRAGMENT_IDENTITIES,
        *_PAGE_TITLE_ROUTE_IDENTIFIER_IDENTITIES,
    }
)

_PUBLIC_COMPOSE_INSPECTION_TEST_SENTINEL_IDENTITIES = frozenset(
    {
        (
            "tests/test_live_nats_transport.py",
            "Secret Keyword",
            (
                *(74, 70, 48, 200, 151, 59, 103, 95, 251, 150),
                *(7, 200, 234, 230, 69, 166, 253, 9, 215, 53),
            ),
        ),
    }
)

_SYNTHETIC_ACHIEVEMENT_URL_TEST_FIXTURE_IDENTITIES = frozenset(
    {
        (
            "frontend/src/components/profile/__tests__/profileUtils.closure.test.ts",
            "Basic Auth Credentials",
            (
                *(157, 78, 30, 35, 189, 91, 114, 112, 70, 169),
                *(227, 180, 183, 219, 87, 189, 141, 110, 230, 132),
            ),
        ),
    }
)


_AUTH_VALIDATION_UI_COPY_IDENTITIES = frozenset(
    {
        (
            "frontend/src/i18n/locales/en/auth.json",
            "Secret Keyword",
            (
                *(62, 125, 86, 169, 88, 4, 255, 60, 50, 43),
                *(151, 167, 231, 205, 186, 37, 220, 146, 9, 87),
            ),
        ),
        (
            "frontend/src/i18n/locales/en/auth.json",
            "Secret Keyword",
            (
                *(81, 214, 154, 230, 4, 109, 42, 59, 226, 69),
                *(68, 157, 91, 56, 22, 93, 93, 120, 222, 245),
            ),
        ),
        (
            "frontend/src/i18n/locales/en/auth.json",
            "Secret Keyword",
            (
                *(214, 156, 59, 26, 197, 75, 231, 218, 54, 102),
                *(217, 147, 123, 156, 120, 231, 195, 9, 214, 232),
            ),
        ),
    }
)

_AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES = frozenset(
    {
        (
            "tests/test_aud253_private_env_files.py",
            "Base64 High Entropy String",
            (
                249,
                234,
                225,
                154,
                241,
                219,
                19,
                25,
                164,
                195,
                226,
                60,
                70,
                145,
                159,
                13,
                181,
                232,
                96,
                104,
            ),
        ),
        (
            "tests/test_aud253_private_env_files.py",
            "Base64 High Entropy String",
            (
                209,
                97,
                7,
                76,
                56,
                168,
                75,
                219,
                177,
                81,
                156,
                145,
                146,
                126,
                11,
                18,
                227,
                102,
                242,
                240,
            ),
        ),
        (
            "tests/test_aud253_private_env_files.py",
            "Base64 High Entropy String",
            (
                237,
                247,
                83,
                211,
                2,
                60,
                48,
                7,
                117,
                85,
                234,
                204,
                176,
                92,
                16,
                249,
                59,
                248,
                247,
                232,
            ),
        ),
        (
            "tests/test_aud253_private_env_files.py",
            "Base64 High Entropy String",
            (
                39,
                64,
                185,
                186,
                132,
                70,
                33,
                101,
                34,
                113,
                107,
                165,
                89,
                20,
                200,
                218,
                104,
                254,
                31,
                74,
            ),
        ),
        (
            "tests/test_aud253_private_env_files.py",
            "Base64 High Entropy String",
            (
                34,
                37,
                215,
                151,
                209,
                211,
                130,
                49,
                24,
                25,
                155,
                23,
                171,
                12,
                127,
                17,
                161,
                125,
                42,
                47,
            ),
        ),
    }
)

_TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES = frozenset(
    {
        (
            "scripts/quality/validate_trivy_kyverno_fixture.py",
            "Hex High Entropy String",
            (
                208,
                194,
                211,
                202,
                127,
                191,
                176,
                34,
                28,
                45,
                65,
                104,
                252,
                218,
                78,
                167,
                15,
                212,
                3,
                158,
            ),
        ),
        (
            "scripts/quality/validate_trivy_kyverno_fixture.py",
            "Hex High Entropy String",
            (
                224,
                192,
                166,
                76,
                174,
                89,
                98,
                209,
                14,
                59,
                156,
                41,
                28,
                44,
                108,
                70,
                149,
                242,
                195,
                91,
            ),
        ),
    }
)

_TRIVY_KYVERNO_PUBLIC_CHECKSUM_DIGESTS = frozenset(
    identity[2] for identity in _TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
)
_AUD253_PRIVATE_ENV_MODE_TEST_DIGESTS = frozenset(
    identity[2] for identity in _AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES
)
_AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_IDENTITIES = frozenset(
    {
        (
            "tests/test_cache_object_keys_aud495.py",
            "Secret Keyword",
            (
                158,
                96,
                27,
                174,
                156,
                212,
                227,
                7,
                93,
                85,
                133,
                139,
                237,
                131,
                255,
                78,
                75,
                253,
                255,
                16,
            ),
        ),
        (
            "tests/test_cache_object_keys_aud495.py",
            "Secret Keyword",
            (
                206,
                224,
                34,
                26,
                248,
                78,
                22,
                250,
                97,
                128,
                240,
                96,
                14,
                161,
                75,
                225,
                205,
                151,
                196,
                143,
            ),
        ),
    }
)
_AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_DIGESTS = frozenset(
    identity[2] for identity in _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_IDENTITIES
)
_AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH = "tests/test_cache_object_keys_aud495.py"
_AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY = (
    "aud495_cache_key_redaction_test_fixture"
)
_TRIVY_KYVERNO_VALIDATOR_PATH = "scripts/quality/validate_trivy_kyverno_fixture.py"

_PUBLIC_IMMUTABLE_315_POLICY_PREFIX_PATH = "tests/test_verify_secrets_baseline.py"
_PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITY = (
    _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_PATH,
    _FALSE_POSITIVE_ALLOWED_TYPE,
    (
        121,
        18,
        205,
        213,
        192,
        120,
        136,
        208,
        61,
        126,
        251,
        249,
        119,
        59,
        133,
        113,
        22,
        198,
        10,
        132,
    ),
)
_PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITIES = frozenset(
    {_PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITY}
)
_PUBLIC_IMMUTABLE_315_POLICY_PREFIX_DIGESTS = frozenset(
    {_PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITY[2]}
)
_PUBLIC_IMMUTABLE_315_POLICY_PREFIX_EVIDENCE_MARKERS = {
    _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITY: (
        "Public SHA-256 integrity digest of immutable 315-record disposition prefix",
        "source-contract test guard in tests/test_verify_secrets_baseline.py",
        "not credential material",
    ),
}

_TRIVY_KYVERNO_EXACT_EVIDENCE_MARKERS = {
    (
        "scripts/quality/validate_trivy_kyverno_fixture.py",
        "Hex High Entropy String",
        (
            208,
            194,
            211,
            202,
            127,
            191,
            176,
            34,
            28,
            45,
            65,
            104,
            252,
            218,
            78,
            167,
            15,
            212,
            3,
            158,
        ),
    ): (
        "Public integrity checksum",
        "public SHA-256 checksum of the pinned Kyverno fixture bytes",
        "not credential material",
    ),
    (
        "scripts/quality/validate_trivy_kyverno_fixture.py",
        "Hex High Entropy String",
        (
            224,
            192,
            166,
            76,
            174,
            89,
            98,
            209,
            14,
            59,
            156,
            41,
            28,
            44,
            108,
            70,
            149,
            242,
            195,
            91,
        ),
    ): (
        "Public integrity checksum",
        "public SHA-256 checksum of the complete candidate Trivy ignore policy",
        "not credential material",
    ),
}

_FALSE_POSITIVE_EXACT_CATEGORY_IDENTITIES = {
    "synthetic_achievement_url_test_fixture": (
        _SYNTHETIC_ACHIEVEMENT_URL_TEST_FIXTURE_IDENTITIES
    ),
    "public_compose_inspection_test_sentinel": (
        _PUBLIC_COMPOSE_INSPECTION_TEST_SENTINEL_IDENTITIES
    ),
    "external_kubernetes_secret_reference": _EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES,
    "source_contract_identifier": _SOURCE_CONTRACT_IDENTIFIER_IDENTITIES,
    "auth_validation_ui_copy": _AUTH_VALIDATION_UI_COPY_IDENTITIES,
    "aud253_private_env_mode_test_fixture": (
        _AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES
    ),
    "aud495_cache_key_redaction_test_fixture": (
        _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_IDENTITIES
    ),
}
_FALSE_POSITIVE_IDENTITY_FIELDS = frozenset({"path", "type", "hashed_secret_bytes"})
_FALSE_POSITIVE_RECORD_FIELDS = frozenset(
    {
        "identity",
        "category",
        "evidence",
        "owner",
        "reviewed_on",
        "expires_on",
        "approval_status",
    }
)
_FALSE_POSITIVE_DOCUMENT_FIELDS = frozenset({"schema_version", "records"})
_FALSE_POSITIVE_POLICY_PATH = "quality/security-false-positive-dispositions.json"
_FALSE_POSITIVE_RECORD_LIMIT = 512
_FALSE_POSITIVE_EVIDENCE_LIMIT = 1000
_FALSE_POSITIVE_OWNER_LIMIT = 120
_FALSE_POSITIVE_PLACEHOLDER_OWNERS = frozenset(
    {"", "owner", "pending", "tbd", "unknown", "n/a", "todo"}
)
_DISPOSITION_WILDCARDS = frozenset("*?[]")


def _decode_git_quoted_path(value: str) -> str:
    """Decode Git's C-quoted pathname form without interpreting source text."""

    if not (value.startswith('"') and value.endswith('"')):
        return value

    escaped = value[1:-1]
    decoded = bytearray()
    simple_escapes = {
        '"': b'"',
        "\\": b"\\",
        "a": b"\a",
        "b": b"\b",
        "f": b"\f",
        "n": b"\n",
        "r": b"\r",
        "t": b"\t",
        "v": b"\v",
    }
    index = 0
    while index < len(escaped):
        character = escaped[index]
        if character != "\\":
            decoded.extend(character.encode("utf-8", errors="surrogateescape"))
            index += 1
            continue

        index += 1
        if index >= len(escaped):
            raise SourceDeltaError("malformed quoted Git pathname")
        escape = escaped[index]
        if escape in simple_escapes:
            decoded.extend(simple_escapes[escape])
            index += 1
            continue
        if escape not in "01234567":
            raise SourceDeltaError("unsupported quoted Git pathname escape")

        digits = escape
        index += 1
        while index < len(escaped) and len(digits) < 3 and escaped[index] in "01234567":
            digits += escaped[index]
            index += 1
        decoded.append(int(digits, 8))

    return decoded.decode("utf-8", errors="surrogateescape")


def _path_from_added_file_header(header: str) -> str | None:
    # Git uses a literal tab after a quoted pathname as its header delimiter;
    # tabs inside a quoted pathname are escaped and are therefore preserved.
    raw_path = header[4:].split("\t", 1)[0]
    if raw_path == "/dev/null":
        return None
    if raw_path.startswith('"'):
        path = _decode_git_quoted_path(raw_path)
    else:
        path = raw_path
    if not path.startswith("b/"):
        raise SourceDeltaError("unexpected Git diff path prefix")
    return path[2:]


def _find_added_inline_secret_pragmas(diff_text: str) -> list[tuple[str, int]]:
    """Return only safe path/line identities for newly added marker lines."""

    findings: list[tuple[str, int]] = []
    current_path: str | None = None
    new_line_number: int | None = None

    lines = diff_text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for line in lines:
        if line.startswith("diff --git "):
            current_path = None
            new_line_number = None
            continue

        if new_line_number is None and line.startswith("+++ "):
            current_path = _path_from_added_file_header(line)
            continue

        hunk = _DIFF_HUNK_PATTERN.match(line)
        if line.startswith("@@"):
            if hunk is None:
                raise SourceDeltaError("unrecognized Git diff hunk header")
            new_line_number = int(hunk.group(1))
            continue

        if new_line_number is None:
            if line.startswith("+") and not line.startswith("+++ "):
                raise SourceDeltaError("Git diff addition has no hunk header")
            continue

        if line.startswith("+"):
            if current_path is None:
                raise SourceDeltaError("Git diff addition has no destination path")
            if _INLINE_SECRET_ALLOWLIST_PATTERN.search(line[1:]) is not None:
                findings.append((current_path, new_line_number))
            new_line_number += 1
        elif line.startswith("-"):
            continue
        elif line.startswith(" "):
            new_line_number += 1
        elif line.startswith("\\ No newline at end of file"):
            continue
        else:
            raise SourceDeltaError("unrecognized Git diff hunk format")

    return findings


def find_new_inline_secret_pragmas(
    trusted_base_sha: str, *, repository_root: str | Path
) -> list[tuple[str, int]]:
    """Compare two immutable Git trees and find newly added suppression markers.

    The trusted base must be a full, nonzero commit SHA. Git diagnostics and
    source lines are never returned to the caller.
    """

    if (
        not isinstance(trusted_base_sha, str)
        or _SOURCE_SHA_PATTERN.fullmatch(trusted_base_sha) is None
        or trusted_base_sha == "0" * 40
    ):
        raise SourceDeltaError("trusted source base SHA is invalid")

    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SourceDeltaError("repository root is unavailable") from error

    git_executable = shutil.which("git")
    if git_executable is None:
        raise SourceDeltaError("Git source comparison could not run")
    try:
        git_executable = str(Path(git_executable).resolve(strict=True))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SourceDeltaError("Git source comparison could not run") from error

    def run_git(*arguments: str) -> str:
        try:
            # Git arguments are fixed except for the already-validated full source SHA.
            # The executable is absolute and shell interpretation is disabled.
            result = subprocess.run(  # noqa: S603
                [git_executable, *arguments],
                cwd=root,
                capture_output=True,
                check=False,
                shell=False,
            )
        except (OSError, UnicodeError) as error:
            raise SourceDeltaError("Git source comparison could not run") from error
        if result.returncode != 0:
            raise SourceDeltaError("Git source comparison failed")
        try:
            return result.stdout.decode("utf-8", errors="surrogateescape")
        except UnicodeError as error:
            raise SourceDeltaError(
                "Git source comparison could not be decoded"
            ) from error

    run_git("cat-file", "-e", f"{trusted_base_sha}^{{commit}}")
    head_sha = run_git("rev-parse", "--verify", "HEAD^{commit}").strip()
    if _SOURCE_SHA_PATTERN.fullmatch(head_sha) is None:
        raise SourceDeltaError("current source commit is unavailable")

    diff_text = run_git(
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--unified=0",
        "--no-renames",
        "--text",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        trusted_base_sha,
        head_sha,
        "--",
    )
    return _find_added_inline_secret_pragmas(diff_text)


@dataclass(frozen=True, slots=True)
class FindingIdentity:
    """Stable, non-secret identity used when comparing detector findings."""

    path: str
    finding_type: str
    hashed_secret: str
    # Detector line numbers are useful diagnostics but are not stable identity:
    # inserting an unrelated line must not require a baseline rewrite.
    line_number: int = field(compare=False, hash=False)

    def sort_key(self) -> tuple[str, int, str, str]:
        """Return a deterministic ordering without exposing the digest."""

        return (self.path, self.line_number, self.finding_type, self.hashed_secret)

    def display(self) -> str:
        """Return a safe diagnostic label (never the secret or its digest)."""

        return f"{self.path}:{self.line_number} ({self.finding_type})"


def canonical_path(value: str) -> str:
    """Return the repository path spelling shared by Windows and POSIX jobs.

    This small helper intentionally lives in the executable verifier as well
    as ``scripts.secrets_baseline``: invoking this file directly puts the
    ``scripts`` directory (rather than the repository root) on ``sys.path``.
    Keeping the verifier standalone avoids a fragile import-time path hack.
    """

    return "/".join(part for part in value.replace("\\", "/").split("/") if part)


def load_json(path: str | Path) -> Any:
    """Load JSON using an explicit encoding and fail closed on I/O errors."""

    try:
        with Path(path).open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as error:
        raise BaselineArtifactError(f"file not found: {error}") from error
    except json.JSONDecodeError as error:
        raise BaselineArtifactError(f"invalid JSON: {error}") from error
    except UnicodeError as error:
        raise BaselineArtifactError(f"invalid UTF-8: {error}") from error
    except OSError as error:
        raise BaselineArtifactError(f"unable to read artifact: {error}") from error


def _canonical_result_path(raw_path: object, *, artifact: str) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise BaselineArtifactError(
            f"{artifact}: result paths must be non-empty strings"
        )

    # Inspect the separator-normalised spelling before dropping duplicate
    # separators so absolute POSIX and UNC paths cannot be reinterpreted as
    # repository-relative paths by canonicalisation.
    normalised_raw_path = raw_path.replace("\\", "/")
    if normalised_raw_path.startswith("/") or re.match(
        r"^[A-Za-z]:", normalised_raw_path
    ):
        raise BaselineArtifactError(
            f"{artifact}: result path must be a normalised repository-relative path"
        )

    path = canonical_path(raw_path)
    # Artifacts are repository-relative.  Reject absolute paths, drive-letter
    # paths, and traversal segments rather than silently normalising them.
    if (
        not path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        raise BaselineArtifactError(
            f"{artifact}: result path must be a normalised repository-relative path"
        )
    return path


def _parse_finding(
    result_path: str,
    raw_finding: object,
    *,
    artifact: str,
    index: int,
) -> FindingIdentity:
    if not isinstance(raw_finding, dict):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] must be an object"
        )

    finding_type = raw_finding.get("type")
    if not isinstance(finding_type, str) or not finding_type.strip():
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid type"
        )

    hashed_secret = raw_finding.get("hashed_secret")
    if not isinstance(hashed_secret, str) or not hashed_secret.strip():
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid hashed_secret"
        )

    line_number = raw_finding.get("line_number")
    if (
        isinstance(line_number, bool)
        or not isinstance(line_number, int)
        or line_number < 1
    ):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid line_number"
        )

    filename = raw_finding.get("filename")
    if filename is not None:
        canonical_filename = _canonical_result_path(filename, artifact=artifact)
        if canonical_filename != result_path:
            raise BaselineArtifactError(
                f"{artifact}: finding {result_path}[{index}] filename does not match its result path"
            )

    verified = raw_finding.get("is_verified")
    if verified is not None and not isinstance(verified, bool):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid is_verified flag"
        )

    return FindingIdentity(result_path, finding_type, hashed_secret, line_number)


def extract_findings(document: object, *, artifact: str) -> set[FindingIdentity]:
    """Validate a detect-secrets document and return deduplicated identities."""

    if not isinstance(document, dict):
        raise BaselineArtifactError(
            f"{artifact}: top-level JSON value must be an object"
        )

    version = document.get("version")
    if not isinstance(version, str) or not version.strip():
        raise BaselineArtifactError(f"{artifact}: version must be a non-empty string")

    raw_results = document.get("results")
    if not isinstance(raw_results, dict):
        raise BaselineArtifactError(f"{artifact}: results must be an object")

    findings: set[FindingIdentity] = set()
    for raw_path, raw_findings in raw_results.items():
        result_path = _canonical_result_path(raw_path, artifact=artifact)
        if not isinstance(raw_findings, list):
            raise BaselineArtifactError(
                f"{artifact}: results for {result_path} must be a list"
            )
        for index, raw_finding in enumerate(raw_findings):
            findings.add(
                _parse_finding(
                    result_path,
                    raw_finding,
                    artifact=artifact,
                    index=index,
                )
            )
    return findings


def validate_baseline_triage(document: object) -> None:
    """Require an explicit false-positive decision for every baseline entry.

    A baseline entry is an allowlist record, not proof that a detector hit was
    reviewed.  ``detect-secrets audit`` records that decision in ``is_secret``;
    keeping the field explicit prevents an unknown finding from silently
    becoming a long-lived suppression.  A committed baseline may contain only
    findings confirmed to be non-secrets.  Real credentials must be removed or
    rotated instead of being labelled as acceptable repository content.
    """

    if not isinstance(document, dict):
        raise BaselineArtifactError("baseline: top-level JSON value must be an object")
    raw_results = document.get("results")
    if not isinstance(raw_results, dict):
        raise BaselineArtifactError("baseline: results must be an object")
    for raw_path, raw_findings in raw_results.items():
        result_path = _canonical_result_path(raw_path, artifact="baseline")
        if not isinstance(raw_findings, list):
            raise BaselineArtifactError(
                f"baseline: findings for {result_path} must be a list"
            )
        for index, raw_finding in enumerate(raw_findings):
            if not isinstance(raw_finding, dict):
                raise BaselineArtifactError(
                    f"baseline: finding {result_path}[{index}] must be an object"
                )
            decision = raw_finding.get("is_secret")
            if decision is not False:
                raise BaselineArtifactError(
                    f"baseline: finding {result_path}[{index}] requires explicit "
                    "is_secret=false triage"
                )


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def validate_false_positive_dispositions(
    document: object, *, today: date | None = None
) -> set[FindingIdentity]:
    """Validate exact dispositions without claiming their source is trusted.

    Callers must select immutable trusted-base data by default. Candidate data
    is valid only after the explicit owner-authored update gate succeeds. The
    closed schema accepts reviewed identities with finite expiry metadata.
    """

    artifact = "false-positive dispositions"
    if (
        not isinstance(document, dict)
        or set(document) != _FALSE_POSITIVE_DOCUMENT_FIELDS
    ):
        raise BaselineArtifactError(f"{artifact}: document schema is invalid")
    version = document.get("schema_version")
    if type(version) is not int or version != 1:
        raise BaselineArtifactError(f"{artifact}: schema version is invalid")
    records = document.get("records")
    if not isinstance(records, list) or len(records) > _FALSE_POSITIVE_RECORD_LIMIT:
        raise BaselineArtifactError(f"{artifact}: record list is invalid")

    current_date = today or date.today()
    findings: set[FindingIdentity] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != _FALSE_POSITIVE_RECORD_FIELDS:
            raise BaselineArtifactError(f"{artifact}: record schema is invalid")
        identity = record.get("identity")
        if (
            not isinstance(identity, dict)
            or set(identity) != _FALSE_POSITIVE_IDENTITY_FIELDS
        ):
            raise BaselineArtifactError(f"{artifact}: identity schema is invalid")

        raw_path = identity.get("path")
        if (
            not isinstance(raw_path, str)
            or any(marker in raw_path for marker in _DISPOSITION_WILDCARDS)
            or any(
                ord(character) < 32 or ord(character) == 127 for character in raw_path
            )
        ):
            raise BaselineArtifactError(f"{artifact}: identity path is invalid")
        path = _canonical_result_path(raw_path, artifact=artifact)
        if path != raw_path:
            raise BaselineArtifactError(f"{artifact}: identity path is not canonical")

        finding_type = identity.get("type")
        raw_digest_bytes = identity.get("hashed_secret_bytes")
        if (
            not isinstance(finding_type, str)
            or not finding_type
            or not isinstance(raw_digest_bytes, list)
            or len(raw_digest_bytes) != 20
            or any(
                type(byte) is not int or not 0 <= byte <= 255
                for byte in raw_digest_bytes
            )
        ):
            raise BaselineArtifactError(f"{artifact}: identity is not supported")
        hashed_secret = bytes(raw_digest_bytes).hex()

        category = record.get("category")
        if not isinstance(category, str) or category not in _FALSE_POSITIVE_CATEGORIES:
            raise BaselineArtifactError(f"{artifact}: category is invalid")
        exact_source_identity = (
            path,
            finding_type,
            tuple(raw_digest_bytes),
        )
        if tuple(raw_digest_bytes) in _AUD253_PRIVATE_ENV_MODE_TEST_DIGESTS and (
            exact_source_identity
            not in _AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES
            or category != "aud253_private_env_mode_test_fixture"
        ):
            raise BaselineArtifactError(
                f"{artifact}: AUD-253 private env fixture identity changed scope"
            )
        if (
            path == _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH
            and finding_type == "Secret Keyword"
            and (
                exact_source_identity
                not in _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_IDENTITIES
                or category != _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
            )
        ):
            raise BaselineArtifactError(
                f"{artifact}: AUD-495 cache-key fixture identity changed scope"
            )
        if tuple(
            raw_digest_bytes
        ) in _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_DIGESTS and (
            exact_source_identity
            not in _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_IDENTITIES
            or category != _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
        ):
            raise BaselineArtifactError(
                f"{artifact}: AUD-495 cache-key fixture identity changed scope"
            )

        if (
            (
                path == _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_PATH
                and finding_type == _FALSE_POSITIVE_ALLOWED_TYPE
            )
            or tuple(raw_digest_bytes) in _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_DIGESTS
        ) and (
            exact_source_identity not in _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITIES
            or category != "public_integrity_digest"
        ):
            raise BaselineArtifactError(
                f"{artifact}: immutable policy-prefix digest identity changed scope"
            )
        if tuple(raw_digest_bytes) in _TRIVY_KYVERNO_PUBLIC_CHECKSUM_DIGESTS and (
            exact_source_identity not in _TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
            or category != "public_integrity_digest"
        ):
            raise BaselineArtifactError(
                f"{artifact}: Trivy Kyverno checksum identity changed scope"
            )
        if (
            exact_source_identity in _PUBLIC_COMPOSE_INSPECTION_TEST_SENTINEL_IDENTITIES
            and category != "public_compose_inspection_test_sentinel"
        ):
            raise BaselineArtifactError(
                f"{artifact}: public Compose sentinel changed category"
            )
        if (
            exact_source_identity in _SOURCE_CONTRACT_IDENTIFIER_IDENTITIES
            and category != "source_contract_identifier"
        ):
            raise BaselineArtifactError(
                f"{artifact}: exact source-contract identity changed category"
            )
        if (
            exact_source_identity in _SYNTHETIC_ACHIEVEMENT_URL_TEST_FIXTURE_IDENTITIES
            and category != "synthetic_achievement_url_test_fixture"
        ):
            raise BaselineArtifactError(
                f"{artifact}: synthetic achievement URL fixture changed category"
            )
        if (
            exact_source_identity in _AUTH_VALIDATION_UI_COPY_IDENTITIES
            and category != "auth_validation_ui_copy"
        ):
            raise BaselineArtifactError(
                f"{artifact}: auth validation UI copy identity changed category"
            )
        if category in _FALSE_POSITIVE_HEX_CATEGORIES:
            category_matches = finding_type == _FALSE_POSITIVE_ALLOWED_TYPE
            if (
                category == "public_integrity_digest"
                and path == _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_PATH
            ):
                category_matches = (
                    category_matches
                    and exact_source_identity
                    in _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITIES
                )
            if (
                category == "public_integrity_digest"
                and path == _TRIVY_KYVERNO_VALIDATOR_PATH
            ):
                category_matches = (
                    category_matches
                    and exact_source_identity
                    in _TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
                )
            if category == "independent_contract_fingerprint":
                exact_v4_identity = (
                    path,
                    finding_type,
                    tuple(raw_digest_bytes),
                ) in _V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES
                category_matches = category_matches and (
                    path == _INDEPENDENT_CONTRACT_FINGERPRINT_PATH or exact_v4_identity
                )
        elif category in _FALSE_POSITIVE_EXACT_IDENTITY_CATEGORIES:
            exact_identities = _FALSE_POSITIVE_EXACT_CATEGORY_IDENTITIES.get(
                category, frozenset()
            )
            category_matches = (
                path,
                finding_type,
                tuple(raw_digest_bytes),
            ) in exact_identities
        else:
            allowed_pairs = _FALSE_POSITIVE_NON_HEX_CATEGORY_PATH_TYPES.get(
                category, frozenset()
            )
            category_matches = (path, finding_type) in allowed_pairs
        if not category_matches:
            raise BaselineArtifactError(
                f"{artifact}: category does not allow this path and detector type"
            )
        evidence = record.get("evidence")
        if (
            not isinstance(evidence, str)
            or not evidence.strip()
            or evidence != evidence.strip()
            or len(evidence) > _FALSE_POSITIVE_EVIDENCE_LIMIT
            or any(
                ord(character) < 32 or ord(character) == 127 for character in evidence
            )
        ):
            raise BaselineArtifactError(f"{artifact}: evidence is invalid")
        required_evidence = _FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS.get(category, ())
        required_evidence += _TRIVY_KYVERNO_EXACT_EVIDENCE_MARKERS.get(
            exact_source_identity, ()
        )
        required_evidence += _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_EVIDENCE_MARKERS.get(
            exact_source_identity, ()
        )
        if any(
            marker.casefold() not in evidence.casefold() for marker in required_evidence
        ):
            raise BaselineArtifactError(
                f"{artifact}: evidence does not resolve the category scope"
            )

        owner = record.get("owner")
        if (
            not isinstance(owner, str)
            or not owner.strip()
            or owner != owner.strip()
            or len(owner) > _FALSE_POSITIVE_OWNER_LIMIT
            or owner.casefold() in _FALSE_POSITIVE_PLACEHOLDER_OWNERS
            or any(ord(character) < 32 or ord(character) == 127 for character in owner)
        ):
            raise BaselineArtifactError(f"{artifact}: owner metadata is invalid")
        if record.get("approval_status") != "approved":
            raise BaselineArtifactError(f"{artifact}: record is not approved")

        raw_reviewed = record.get("reviewed_on")
        raw_expires = record.get("expires_on")
        if not isinstance(raw_reviewed, str) or not isinstance(raw_expires, str):
            raise BaselineArtifactError(f"{artifact}: date metadata is invalid")
        try:
            reviewed_on = date.fromisoformat(raw_reviewed)
            expires_on = date.fromisoformat(raw_expires)
        except ValueError as error:
            raise BaselineArtifactError(
                f"{artifact}: date metadata is invalid"
            ) from error
        if (
            reviewed_on.isoformat() != raw_reviewed
            or expires_on.isoformat() != raw_expires
            or reviewed_on > current_date
            or expires_on < current_date
            or expires_on <= reviewed_on
            or expires_on - reviewed_on > timedelta(days=90)
        ):
            raise BaselineArtifactError(f"{artifact}: date range is invalid")

        if category == "public_compose_inspection_test_sentinel" and expires_on > date(
            2027, 1, 10
        ):
            raise BaselineArtifactError(
                f"{artifact}: public Compose sentinel exceeds approved expiry"
            )

        if category == "synthetic_achievement_url_test_fixture" and expires_on > date(
            2027, 1, 10
        ):
            raise BaselineArtifactError(
                f"{artifact}: synthetic achievement URL fixture exceeds approved expiry"
            )

        if category == "auth_validation_ui_copy" and expires_on > date(2027, 1, 10):
            raise BaselineArtifactError(
                f"{artifact}: auth validation UI copy exceeds approved expiry"
            )

        if category == "aud253_private_env_mode_test_fixture" and expires_on > date(
            2027, 1, 10
        ):
            raise BaselineArtifactError(
                f"{artifact}: AUD-253 private env fixture exceeds approved expiry"
            )

        if (
            category == _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
            and expires_on > date(2027, 1, 10)
        ):
            raise BaselineArtifactError(
                f"{artifact}: AUD-495 cache-key fixture exceeds proposed expiry cap"
            )

        if (
            exact_source_identity in _PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITIES
            and expires_on > date(2027, 1, 10)
        ):
            raise BaselineArtifactError(
                f"{artifact}: immutable policy-prefix digest exceeds proposed expiry"
            )

        if (
            exact_source_identity in _TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
            and expires_on > date(2026, 11, 22)
        ):
            raise BaselineArtifactError(
                f"{artifact}: Trivy Kyverno checksum exceeds approved expiry"
            )

        if (
            category == "source_contract_identifier"
            and exact_source_identity in _PAGE_TITLE_ROUTE_IDENTIFIER_IDENTITIES
            and expires_on > date(2027, 1, 10)
        ):
            raise BaselineArtifactError(
                f"{artifact}: page title route identifier exceeds approved expiry"
            )

        finding = FindingIdentity(path, finding_type, hashed_secret, 1)
        if finding in findings:
            raise BaselineArtifactError(f"{artifact}: duplicate identity")
        findings.add(finding)
    return findings


def load_trusted_base_false_positive_dispositions(
    trusted_base_sha: str,
    *,
    repository_root: str | Path,
    today: date | None = None,
) -> set[FindingIdentity]:
    """Load the optional disposition artifact exclusively from a trusted tree."""

    if (
        not isinstance(trusted_base_sha, str)
        or _SOURCE_SHA_PATTERN.fullmatch(trusted_base_sha) is None
        or trusted_base_sha == "0" * 40
    ):
        raise BaselineArtifactError("trusted source base SHA is invalid")
    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise BaselineArtifactError("repository root is unavailable") from error

    git_executable = shutil.which("git")
    if git_executable is None:
        raise BaselineArtifactError("trusted disposition lookup could not run")
    try:
        git_executable = str(Path(git_executable).resolve(strict=True))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise BaselineArtifactError(
            "trusted disposition lookup could not run"
        ) from error

    def run_git(*arguments: str) -> bytes:
        try:
            # The only variable arguments are the validated commit SHA and a
            # fixed repository-relative artifact path; shell parsing is off.
            result = subprocess.run(  # noqa: S603
                [git_executable, *arguments],
                cwd=root,
                capture_output=True,
                check=False,
                shell=False,
            )
        except (OSError, UnicodeError) as error:
            raise BaselineArtifactError(
                "trusted disposition lookup could not run"
            ) from error
        if result.returncode != 0:
            raise BaselineArtifactError("trusted disposition lookup failed")
        return result.stdout

    try:
        run_git("cat-file", "-e", f"{trusted_base_sha}^{{commit}}")
        tree_entries = (
            run_git(
                "ls-tree",
                "-r",
                "--full-tree",
                trusted_base_sha,
                "--",
                _FALSE_POSITIVE_POLICY_PATH,
            )
            .decode("utf-8")
            .splitlines()
        )
    except UnicodeError as error:
        raise BaselineArtifactError("trusted disposition tree is invalid") from error

    if not tree_entries:
        return set()
    if len(tree_entries) != 1 or "\t" not in tree_entries[0]:
        raise BaselineArtifactError("trusted disposition tree entry is invalid")
    metadata, path = tree_entries[0].rsplit("\t", 1)
    fields = metadata.split()
    if (
        path != _FALSE_POSITIVE_POLICY_PATH
        or len(fields) != 3
        or fields[:2] != ["100644", "blob"]
    ):
        raise BaselineArtifactError("trusted disposition tree entry is invalid")

    try:
        raw_document = run_git(
            "show", f"{trusted_base_sha}:{_FALSE_POSITIVE_POLICY_PATH}"
        )
        if len(raw_document) > 512 * 1024:
            raise BaselineArtifactError(
                "false-positive disposition artifact is too large"
            )
        document = json.loads(
            raw_document.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, BaselineArtifactError):
            raise
        raise BaselineArtifactError(
            "false-positive disposition artifact is invalid"
        ) from error
    return validate_false_positive_dispositions(document, today=today)


def load_owner_authored_candidate_false_positive_dispositions(
    *, repository_root: str | Path, today: date | None = None
) -> set[FindingIdentity]:
    """Load the candidate policy after the trusted workflow owner gate passes."""

    try:
        root = Path(repository_root).resolve(strict=True)
        policy_path = root.joinpath(*_FALSE_POSITIVE_POLICY_PATH.split("/"))
        resolved_policy_path = policy_path.resolve(strict=True)
        if (
            resolved_policy_path != policy_path
            or not resolved_policy_path.is_file()
            or resolved_policy_path.stat().st_size > 512 * 1024
        ):
            raise BaselineArtifactError("candidate disposition artifact is unavailable")
        raw_document = resolved_policy_path.read_bytes()
        document = json.loads(
            raw_document.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except BaselineArtifactError:
        raise
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        raise BaselineArtifactError(
            "candidate disposition artifact is invalid"
        ) from error
    return validate_false_positive_dispositions(document, today=today)


def _describe_findings(findings: set[FindingIdentity]) -> str:
    """Render bounded, deterministic diagnostics without secret material."""

    ordered = sorted(findings, key=FindingIdentity.sort_key)
    preview = ", ".join(finding.display() for finding in ordered[:20])
    if len(ordered) > 20:
        preview += f", ... (+{len(ordered) - 20} more)"
    return preview


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a detect-secrets baseline against a fresh scan."
    )
    parser.add_argument("baseline_path", help="committed detect-secrets baseline")
    parser.add_argument("current_scan_path", help="fresh detect-secrets scan")
    parser.add_argument(
        "--trusted-base-baseline",
        "--base-baseline",
        dest="trusted_base_baseline",
        help="trusted target-branch baseline used to detect new PR suppressions",
    )
    parser.add_argument(
        "--trusted-base-source-sha",
        help="immutable trusted source commit used to detect new inline suppressions",
    )
    parser.add_argument(
        "--trusted-disposition-source-sha",
        help="trusted commit whose false-positive disposition artifact is loaded",
    )
    parser.add_argument(
        "--owner-authored-disposition-update",
        action="store_true",
        help="use candidate dispositions only after the trusted owner-policy gate passes",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify baseline findings and return a shell-friendly status code."""

    try:
        arguments = _build_parser().parse_args(argv)
    except SystemExit as error:
        # Keep the function convenient for tests while retaining argparse's
        # normal CLI help/usage output and exit status.
        return int(error.code) if isinstance(error.code, int) else 2

    try:
        baseline_document = load_json(arguments.baseline_path)
        validate_baseline_triage(baseline_document)
        baseline_findings = extract_findings(baseline_document, artifact="baseline")
        current_findings = extract_findings(
            load_json(arguments.current_scan_path), artifact="current scan"
        )
        trusted_findings: set[FindingIdentity] | None = None
        if arguments.trusted_base_baseline is not None:
            trusted_findings = extract_findings(
                load_json(arguments.trusted_base_baseline), artifact="trusted base"
            )
    except BaselineArtifactError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    source_pragma_findings: list[tuple[str, int]] = []
    if arguments.trusted_base_source_sha is not None:
        try:
            source_pragma_findings = find_new_inline_secret_pragmas(
                arguments.trusted_base_source_sha,
                repository_root=Path(__file__).resolve().parents[1],
            )
        except SourceDeltaError:
            print(
                "ERROR: trusted source delta could not be verified.",
                file=sys.stderr,
            )
            return 2
    if (
        arguments.owner_authored_disposition_update
        and arguments.trusted_base_source_sha is None
    ):
        print(
            "ERROR: owner-authored disposition mode requires a trusted source base.",
            file=sys.stderr,
        )
        return 2
    if (
        arguments.trusted_disposition_source_sha is not None
        and arguments.trusted_base_source_sha is None
    ):
        print(
            "ERROR: trusted dispositions require a trusted source base.",
            file=sys.stderr,
        )
        return 2

    trusted_dispositions: set[FindingIdentity] = set()
    disposition_source_sha = (
        arguments.trusted_disposition_source_sha or arguments.trusted_base_source_sha
    )
    if disposition_source_sha is not None:
        try:
            if arguments.owner_authored_disposition_update:
                trusted_dispositions = (
                    load_owner_authored_candidate_false_positive_dispositions(
                        repository_root=Path(__file__).resolve().parents[1]
                    )
                )
            else:
                trusted_dispositions = load_trusted_base_false_positive_dispositions(
                    disposition_source_sha,
                    repository_root=Path(__file__).resolve().parents[1],
                )
        except BaselineArtifactError:
            print(
                "ERROR: trusted false-positive dispositions could not be verified.",
                file=sys.stderr,
            )
            return 2

    new_findings = current_findings - baseline_findings - trusted_dispositions
    stale_suppressions = baseline_findings - current_findings
    # Only a newly added baseline entry that actually suppresses a finding in
    # this scan changes security semantics.  New stale entries remain harmless
    # and retain the existing removal/refactoring behaviour.
    new_trusted_suppressions: set[FindingIdentity] = set()
    if trusted_findings is not None:
        new_trusted_suppressions = (
            baseline_findings - trusted_findings
        ) & current_findings

    if stale_suppressions:
        print(
            "INFO: .secrets.baseline contains "
            f"{len(stale_suppressions)} stale finding(s) "
            "(removed files or secrets are allowed)."
        )

    matched_dispositions = current_findings & trusted_dispositions
    if matched_dispositions:
        print(
            "INFO: trusted base reviewed "
            f"{len(matched_dispositions)} exact false-positive finding(s)."
        )

    if new_findings:
        print(
            "ERROR: current scan contains "
            f"{len(new_findings)} new finding(s) not present in the "
            "committed baseline: "
            f"{_describe_findings(new_findings)}",
            file=sys.stderr,
        )

    if new_trusted_suppressions:
        print(
            "ERROR: baseline introduces "
            f"{len(new_trusted_suppressions)} finding-level suppression(s) relative "
            "to the trusted base baseline: "
            f"{_describe_findings(new_trusted_suppressions)}",
            file=sys.stderr,
        )

    if source_pragma_findings:
        print(
            "ERROR: source delta adds "
            f"{len(source_pragma_findings)} inline secret-allowlist pragma line(s).",
            file=sys.stderr,
        )

    if new_findings or new_trusted_suppressions or source_pragma_findings:
        return 1

    baseline_paths = {finding.path for finding in baseline_findings}
    print(
        "OK: .secrets.baseline integrity check passed "
        f"({len(baseline_paths)} suppressed file(s), "
        f"{len(baseline_findings)} finding(s) verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
