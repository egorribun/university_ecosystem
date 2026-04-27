"""Feature flag evaluation via OpenFeature + flagd.

MOD-21-09 (audit 2026-03-25 Wave 21): Integrates with the existing flagd
deployment (k8s/flagd/) for gradual rollouts, A/B testing, and kill switches.

Usage:
    from app.core.feature_flags import is_enabled

    if await is_enabled("new-chat-ui", context={"user_id": str(user.id)}):
        ...
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Known flag names (sync with k8s/flagd/flags-configmap.yaml) ──────────────

FLAG_NEW_CHAT_UI = "new-chat-ui"
FLAG_SEMANTIC_SEARCH = "semantic-search"
FLAG_PUSH_BATCHING = "push-batching"
FLAG_GRAPHQL_SUBSCRIPTIONS = "graphql-subscriptions"

_provider_initialized = False
_provider_lock = threading.Lock()  # RZ-33-29: DCL per RZ-30-01


def _ensure_provider() -> None:
    """Lazily initialize the OpenFeature provider on first use."""
    global _provider_initialized
    if _provider_initialized:  # RZ-33-29: fast path — no lock after init
        return
    with _provider_lock:  # RZ-33-29: slow path — double-checked locking
        if _provider_initialized:
            return  # type: ignore[unreachable]  # RZ-33-29: DCL — reachable under concurrent access
        try:
            from openfeature import api as of_api
            from openfeature.contrib.provider.flagd import FlagdProvider

            from app.core.config import settings

            host = getattr(settings, "flagd_host", "localhost")
            port = int(getattr(settings, "flagd_port", 8013))

            provider = FlagdProvider(host=host, port=port)
            of_api.set_provider(provider)
            _provider_initialized = True
            logger.info("OpenFeature flagd provider initialized", host=host, port=port)
        except ImportError:
            logger.info(
                "openfeature-sdk or flagd provider not installed — "
                "feature flags will use static defaults"
            )
            _provider_initialized = True  # Don't retry
        except Exception as exc:  # RZ-22-01-JUSTIFIED: optional dependency — flagd init failure degrades to defaults (reviewed TD-27-04)
            logger.warning("Failed to initialize flagd provider: %s", exc)
            _provider_initialized = True  # Don't retry on every call


async def is_enabled(
    flag_name: str,
    *,
    default: bool = False,
    context: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a boolean feature flag.

    Returns the flag value from flagd, or ``default`` if the provider is
    unavailable or the flag is not defined.  This function never raises.
    """
    _ensure_provider()
    try:
        from openfeature import api as of_api
        from openfeature.evaluation_context import EvaluationContext

        client = of_api.get_client()
        eval_ctx = EvaluationContext(attributes=context) if context else None
        result: bool = client.get_boolean_value(flag_name, default, eval_ctx)
        return result
    except ImportError:
        return default
    except Exception as exc:  # RZ-22-01-JUSTIFIED: optional dependency — flag evaluation failure degrades to default (reviewed TD-27-04)
        logger.debug("Feature flag evaluation failed for %s: %s", flag_name, exc)
        return default


def is_enabled_sync(
    flag_name: str,
    *,
    default: bool = False,
    context: dict[str, Any] | None = None,
) -> bool:
    """Synchronous variant for non-async code paths (middleware, config)."""
    _ensure_provider()
    try:
        from openfeature import api as of_api
        from openfeature.evaluation_context import EvaluationContext

        client = of_api.get_client()
        eval_ctx = EvaluationContext(attributes=context) if context else None
        result: bool = client.get_boolean_value(flag_name, default, eval_ctx)
        return result
    except ImportError:
        return default
    except Exception as exc:  # RZ-22-01-JUSTIFIED: optional dependency — flag evaluation failure degrades to default (reviewed TD-27-04)
        logger.debug("Feature flag evaluation failed for %s: %s", flag_name, exc)
        return default


# ── Backward-compatible shim for legacy callers ──────────────────────────────
#
# The old API exposed a module-level ``feature_flags`` object with methods like
# ``.initialize()``, ``.list_flags()``, ``.update()``.  These callers exist in
# ``app/core/lifespan.py`` and ``app/api/admin/feature_flags.py``.
#
# This shim bridges the gap until those callers are migrated to the new API.

_KNOWN_FLAGS = {
    FLAG_NEW_CHAT_UI: False,
    FLAG_SEMANTIC_SEARCH: False,
    FLAG_PUSH_BATCHING: True,
    FLAG_GRAPHQL_SUBSCRIPTIONS: False,
}


class _LegacyFeatureFlagsBridge:
    """Backward-compatible bridge for ``from app.core.feature_flags import feature_flags``."""

    async def initialize(self) -> None:
        _ensure_provider()

    def list_flags(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "enabled": is_enabled_sync(name, default=default)}
            for name, default in _KNOWN_FLAGS.items()
        ]

    async def update(
        self, name: str, *, enabled: bool | None = None, **kwargs: Any
    ) -> dict[str, Any] | None:
        if name not in _KNOWN_FLAGS:
            return None

        logger.warning(
            "feature_flags.update() called — flagd flags are managed via ConfigMap, "
            "not runtime updates.  Flag: %s",
            name,
        )
        # RZ-33-09: use ternary — `or` returns default when enabled is explicitly False.
        resolved = enabled if enabled is not None else _KNOWN_FLAGS.get(name, False)
        return {"name": name, "enabled": resolved}

    def to_dict(self) -> dict[str, Any]:
        return {
            name: is_enabled_sync(name, default=default)
            for name, default in _KNOWN_FLAGS.items()
        }

    async def close(self) -> None:
        pass


feature_flags = _LegacyFeatureFlagsBridge()
