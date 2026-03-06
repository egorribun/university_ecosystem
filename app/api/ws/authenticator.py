import logging

from fastapi import WebSocket

from app.api.ws.auth import (
    extract_bearer_token,
    extract_token_from_subprotocol,
    get_user_from_cookie,
    get_user_from_token,
    select_subprotocol,
)
from app.core.feature_flags import feature_flags
from app.models.models import User
from app.schemas.dtos import UserDTO

logger = logging.getLogger(__name__)


class WsAuthenticator:
    """Handles authentication for WebSocket upgrade requests."""

    async def authenticate_upgrade(
        self, websocket: WebSocket
    ) -> tuple[User | UserDTO | None, str | None, str | None]:
        user = None
        session_jti = None

        auth_header = websocket.headers.get("authorization")
        protocol_header = websocket.headers.get("sec-websocket-protocol")
        header_token = extract_bearer_token(auth_header)
        protocol_token = extract_token_from_subprotocol(protocol_header)
        selected_subprotocol = select_subprotocol(protocol_header)

        if header_token or protocol_token:
            logger.info(
                "Attempting WebSocket token auth from headers (auth=%s, protocol=%s)",
                bool(header_token),
                bool(protocol_token),
            )
            token_str = str(header_token or protocol_token)
            user, session_jti = await get_user_from_token(token_str)
            if user:
                logger.info("Token auth successful: user_id=%s", user.id)
            else:
                logger.warning("Token auth failed: invalid token")

        # Fallback to cookie-based auth
        if not user:
            is_query_param_enabled = feature_flags.of_client.get_boolean_value(
                "websocket_query_param_compat",
                default_value=False,
            )
            if is_query_param_enabled:
                token = websocket.query_params.get("token")
                if token:
                    logger.warning(
                        "SECURITY DEPRECATION: WebSocket token passed via query param. "
                        "This exposure vector will be removed; use Authorization header or "
                        "Sec-WebSocket-Protocol instead. "
                        "Disable websocket_query_param_compat feature flag to block this path."
                    )
                    try:
                        from app.deps.cache import get_cache_client
                        from app.services.fraud_detection_service import (
                            FraudDetectionService,
                        )

                        _rc = await get_cache_client()
                        _fds = FraudDetectionService(_rc)
                        await _fds.record_event(
                            {
                                "event": "ws.token_query_param",
                                "severity": "medium",
                                "client_host": websocket.client.host
                                if websocket.client
                                else "",
                            }
                        )
                    except Exception as exc:
                        logger.debug("Fraud detection event recording failed: %s", exc)
                        pass
                    user, session_jti = await get_user_from_token(token)
                    if user:
                        logger.info("Token auth successful: user_id=%s", user.id)
                    else:
                        logger.warning("Token auth failed: invalid token")

        if not user:
            access_token = websocket.cookies.get("access_token_v2")
            if access_token:
                logger.info("Attempting cookie auth, access_token present: True")
                user, session_jti = await get_user_from_cookie(access_token)
                if user:
                    logger.info("Cookie auth successful: user_id=%s", user.id)
                else:
                    logger.warning("Cookie auth failed: invalid cookie")

        return user, session_jti, selected_subprotocol


authenticator = WsAuthenticator()
