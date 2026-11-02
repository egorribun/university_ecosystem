"""Identity contracts for configuration-free model metadata dependencies."""

from __future__ import annotations

import importlib

from app import models
from app.core import database
from app.core.chat_constants import (
    CHAT_MAX_MESSAGE_LENGTH,
    CHAT_MAX_WEBSOCKET_FRAME_BYTES,
)
from app.core.config import storage
from app.core.db.base import Base
from app.core.db.encryption import EncryptedString, TotpEncryptedString
from app.utils import encryption

_MODEL_MODULES = (
    "auth",
    "chat",
    "chat_send_receipt",
    "cwv",
    "dead_letter",
    "domain_events",
    "events",
    "failed_outbox_events",
    "grade",
    "logs",
    "news",
    "notifications",
    "quarantine",
    "schedule",
    "spotify",
    "stories",
    "tenant",
    "users",
)


def test_runtime_and_all_model_modules_share_the_same_declarative_base() -> None:
    assert database.Base is Base
    assert models.Base is Base
    for module_name in _MODEL_MODULES:
        module = importlib.import_module(f"app.models.{module_name}")
        assert module.Base is Base
        assert module.Base.registry is Base.registry
        assert module.Base.metadata is Base.metadata


def test_runtime_encryption_names_reexport_the_same_sqlalchemy_types() -> None:
    assert encryption.EncryptedString is EncryptedString
    assert encryption.TotpEncryptedString is TotpEncryptedString
    assert isinstance(
        models.SpotifyIntegration.__table__.c.access_token.type, EncryptedString
    )
    assert isinstance(
        models.MfaTotpEnrollment.__table__.c.secret.type, TotpEncryptedString
    )


def test_chat_constants_retain_the_existing_config_import_contract() -> None:
    assert storage.CHAT_MAX_MESSAGE_LENGTH == CHAT_MAX_MESSAGE_LENGTH == 32_768
    assert (
        storage.CHAT_MAX_WEBSOCKET_FRAME_BYTES
        == CHAT_MAX_WEBSOCKET_FRAME_BYTES
        == 60 * 1024
    )
    assert models.Message.__table__.c.content.type.length == CHAT_MAX_MESSAGE_LENGTH
