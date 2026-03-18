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
    # Canonical representation using JSON array avoids delimiter injection (Canonicalization vulnerability)
    timestamp_str = created_at.isoformat()

    payload = json.dumps(
        [
            str(actor_user_id) if actor_user_id else None,
            str(subject_user_id) if subject_user_id else None,
            resource_type,
            resource_id,
            action,
            context,
            ip_address,
            user_agent,
            timestamp_str,
        ],
        separators=(",", ":"),
    )

    primary_secret = settings.audit_log_secret.split(",")[0].strip()
    if not primary_secret:
        raise ValueError("AUDIT_LOG_SECRET must not be empty")

    signature = hmac.new(
        primary_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return signature
