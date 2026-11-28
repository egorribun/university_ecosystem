import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.ws.authenticator import WsAuthenticator
from app.models import User


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["ticket", "cookie"])
async def test_successful_upgrade_logs_auth_method_without_user_id(
    method: str, caplog: pytest.LogCaptureFixture
) -> None:
    websocket = MagicMock()
    websocket.headers = {}
    websocket.query_params = {"ticket": "demo"} if method == "ticket" else {}
    websocket.cookies = {"access_token_v2": "demo"} if method == "cookie" else {}
    user = MagicMock(spec=User, id=uuid4())
    caplog.set_level(logging.INFO, logger="app.api.ws.authenticator")

    with patch(
        f"app.api.ws.authenticator.get_user_from_{method}",
        new=AsyncMock(return_value=(user, "demo-session-marker")),
    ):
        result = await WsAuthenticator().authenticate_upgrade(websocket)

    assert result == (user, "demo-session-marker", None)
    assert f"WS {method} auth successful" in caplog.text
    assert str(user.id) not in caplog.text
