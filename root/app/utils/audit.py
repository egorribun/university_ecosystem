import hmac
import hashlib
import json
from datetime import datetime
from app.core.config import settings

def calculate_log_signature(
    actor_user_id: int | None,
    subject_user_id: int | None,
    resource_type: str,
    resource_id: str | None,
    action: str,
    context: dict,
    ip_address: str | None,
    user_agent: str | None,
    created_at: datetime
) -> str:
    """
    Calculate a deterministic HMAC-SHA256 signature for a DataAccessLog entry.
    """
    # Canonical string representation
    # Sort context keys to ensure deterministic serialization
    context_json = json.dumps(context, sort_keys=True)
    
    # Use ISO format for timestamp to ensure consistency
    timestamp_str = created_at.isoformat()
    
    payload = "|".join([
        str(actor_user_id or ""),
        str(subject_user_id or ""),
        resource_type,
        resource_id or "",
        action,
        context_json,
        ip_address or "",
        user_agent or "",
        timestamp_str
    ])
    
    # Fallback to secret_key if audit_log_secret is not set
    secret = settings.audit_log_secret or settings.secret_key
    
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    return signature
