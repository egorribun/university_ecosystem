import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Any

from app.core.config import settings


def calculate_log_signature(
    actor_user_id: uuid.UUID | int | None,
    subject_user_id: uuid.UUID | int | None,
    resource_type: str,
    resource_id: str | None,
    action: str,
    context: dict[str, Any],
    ip_address: str | None,
    user_agent: str | None,
    created_at: datetime,
) -> str:
    """
    Calculate a deterministic HMAC-SHA256 signature for a DataAccessLog entry.
    """
    # Canonical string representation
    # Sort context keys to ensure deterministic serialization
    context_json = json.dumps(context, sort_keys=True, default=str)

    # Use ISO format for timestamp to ensure consistency
    timestamp_str = created_at.isoformat()

    payload = "|".join(
        [
            str(actor_user_id or ""),
            str(subject_user_id or ""),
            resource_type,
            resource_id or "",
            action,
            context_json,
            ip_address or "",
            user_agent or "",
            timestamp_str,
        ]
    )

    primary_secret = settings.audit_log_secret.split(",")[0].strip()
    if not primary_secret:
        raise ValueError("AUDIT_LOG_SECRET must not be empty")

    signature = hmac.new(
        primary_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return signature
