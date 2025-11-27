import json
import logging
from typing import Any

from fastapi import Request

logger = logging.getLogger("app.audit")


class AuditService:
    def __init__(self):
        self.logger = logger

    def _select_logger(self, event: str) -> logging.Logger:
        """Route audit events to component-specific loggers."""

        if event.startswith("auth."):
            return logging.getLogger("app.auth")
        if event.startswith(("password.", "users.")):
            return logging.getLogger("app.users.audit")
        return self.logger

    def log(
        self,
        event: str,
        request: Request,
        user_id: int | None = None,
        level: int = logging.INFO,
        **kwargs: Any,
    ) -> None:
        payload = {
            "event": event,
            "user_id": str(user_id) if user_id else None,
            "ip": request.client.host if request.client else None,
            "path": request.url.path,
            **kwargs,
        }
        logger = self._select_logger(event)
        logger.log(level, json.dumps(payload), extra=payload)
