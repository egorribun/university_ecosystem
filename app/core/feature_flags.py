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
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Known flag names (sync with k8s/flagd/flags.json) ────────────────────────

FLAG_NEW_CHAT_UI = "new-chat-ui"
FLAG_SEMANTIC_SEARCH = "semantic-search"
FLAG_PUSH_BATCHING = "push-batching"
FLAG_GRAPHQL_SUBSCRIPTIONS = "graphql-subscriptions"

FEATURE_FLAG_CONFIG_PATH = "k8s/flagd/flags.json"
FEATURE_FLAG_MANAGEMENT: Literal["gitops"] = "gitops"


@dataclass(frozen=True, slots=True)
class _FlagDefinition:
    name: str
    default: bool
    description: str


class FeatureFlagSnapshot(TypedDict):
    """Read-only view of one registered flag and its effective evaluation."""

    name: str
    enabled: bool
    default: bool
    description: str
    provider: str
    evaluation_reason: str
    management: Literal["gitops"]
    config_path: str


_FLAG_DEFINITIONS = (
    _FlagDefinition(
        FLAG_NEW_CHAT_UI,
        False,
        "Enable the next-generation chat interface.",
    ),
    _FlagDefinition(
        FLAG_SEMANTIC_SEARCH,
        False,
        "Enable semantic search across indexed university content.",
    ),
    _FlagDefinition(
        FLAG_PUSH_BATCHING,
        True,
        "Batch push notifications before delivery.",
    ),
    _FlagDefinition(
        FLAG_GRAPHQL_SUBSCRIPTIONS,
        False,
        "Enable the experimental GraphQL subscription transport.",
    ),
)

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

            host = settings.integrations.flagd_host
            port = settings.integrations.flagd_port

            provider = FlagdProvider(host=host, port=port)
            of_api.set_provider(provider)
            _provider_initialized = True
            logger.info("OpenFeature flagd provider initialized", host=host, port=port)
        except ImportError:
            logger.error(
                "Required OpenFeature flagd provider is unavailable; "
                "feature flags will use call-site defaults"
            )
            _provider_initialized = True  # Don't retry
        except Exception as exc:  # RZ-22-01-JUSTIFIED: external flagd control-plane failure degrades to defaults (reviewed TD-27-04)
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
    except Exception as exc:  # RZ-22-01-JUSTIFIED: external flagd evaluation failure degrades to default (reviewed TD-27-04)
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
    except Exception as exc:  # RZ-22-01-JUSTIFIED: external flagd evaluation failure degrades to default (reviewed TD-27-04)
        logger.debug("Feature flag evaluation failed for %s: %s", flag_name, exc)
        return default


def _snapshot_from_details(
    definition: _FlagDefinition,
    *,
    enabled: bool,
    provider: str,
    reason: str,
) -> FeatureFlagSnapshot:
    return {
        "name": definition.name,
        "enabled": enabled,
        "default": definition.default,
        "description": definition.description,
        "provider": provider,
        "evaluation_reason": reason,
        "management": FEATURE_FLAG_MANAGEMENT,
        "config_path": FEATURE_FLAG_CONFIG_PATH,
    }


def _unavailable_snapshots() -> list[FeatureFlagSnapshot]:
    return [
        _snapshot_from_details(
            definition,
            enabled=definition.default,
            provider="unavailable",
            reason="ERROR",
        )
        for definition in _FLAG_DEFINITIONS
    ]


def list_feature_flags() -> list[FeatureFlagSnapshot]:
    """Return effective flag values without implying a mutable control plane.

    Flag definitions are owned by the version-controlled flagd ConfigMap.  If
    the provider cannot evaluate an individual flag, that entry explicitly
    reports the registered call-site fallback and ``ERROR`` as its reason.
    """
    _ensure_provider()
    try:
        from openfeature import api as of_api

        provider_metadata = of_api.get_provider_metadata()
        if getattr(provider_metadata, "is_default_provider", False):
            logger.warning(
                "Feature flag diagnostics are using the OpenFeature no-op provider"
            )
            return _unavailable_snapshots()
        client = of_api.get_client()
        provider_name = provider_metadata.name
    except Exception as exc:  # RZ-22-01-JUSTIFIED: read-only diagnostics must remain available when the optional flag control plane is down
        logger.warning("Feature flag diagnostics unavailable: %s", exc)
        return _unavailable_snapshots()

    snapshots: list[FeatureFlagSnapshot] = []
    for definition in _FLAG_DEFINITIONS:
        try:
            details = client.get_boolean_details(definition.name, definition.default)
            snapshots.append(
                _snapshot_from_details(
                    definition,
                    enabled=bool(details.value),
                    provider=provider_name,
                    reason=str(details.reason),
                )
            )
        except Exception as exc:  # RZ-22-01-JUSTIFIED: one malformed/unavailable flag must not hide diagnostics for the remaining registry
            logger.debug(
                "Feature flag diagnostics failed for %s: %s", definition.name, exc
            )
            snapshots.append(
                _snapshot_from_details(
                    definition,
                    enabled=definition.default,
                    provider=provider_name,
                    reason="ERROR",
                )
            )
    return snapshots


async def initialize_feature_flags() -> None:
    """Initialize the process-wide OpenFeature provider during app startup."""
    _ensure_provider()


async def shutdown_feature_flags() -> None:
    """Release provider resources and permit clean initialization in a new lifespan."""
    global _provider_initialized
    try:
        from openfeature import api as of_api

        of_api.shutdown()
    except Exception as exc:  # RZ-22-01-JUSTIFIED: best-effort shutdown must not prevent the rest of application teardown
        logger.warning("Failed to shut down OpenFeature provider: %s", exc)
    finally:
        with _provider_lock:
            _provider_initialized = False
