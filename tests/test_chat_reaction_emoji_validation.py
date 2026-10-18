from __future__ import annotations

import runpy
import sys
import uuid
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter, ValidationError

from app.api.chat import router
from app.api.deps import get_current_user_from_dishka, get_locale
from app.data.emoji import generate as emoji_generator
from app.schemas.chat import ReactionEmoji
from app.services.chat.command_service import ChatMaintenanceService
from app.services.chat.query_service import ChatQueryService
from tests.conftest import build_dishka_app

REACTION_EMOJI_ADAPTER = TypeAdapter(ReactionEmoji)
CHAT_ID = "00000000-0000-0000-0000-000000000001"
MESSAGE_ID = "00000000-0000-0000-0000-000000000002"


def test_reaction_input_accepts_qualified_unicode_emoji_sequences() -> None:
    values = (
        "👍",
        "🫫",
        "❤️",
        "👩🏽‍💻",
        "👨‍👩‍👧‍👦",
        "🇺🇸",
        "1️⃣",
        "😶‍🌫",
    )

    for value in values:
        assert REACTION_EMOJI_ADAPTER.validate_python(value) == value


def test_reaction_input_rejects_text_multiple_or_invalid_sequences() -> None:
    for value in (
        "thanks",
        "👍💙",
        "👍 ❤️",
        "👍‍❤",
        "❤",
        "🏽",
        "\u200d",
        "\ufe0f",
    ):
        with pytest.raises(ValidationError):
            REACTION_EMOJI_ADAPTER.validate_python(value)


def test_unicode_generator_keeps_only_qualified_sequences() -> None:
    fixture = """# Unicode Emoji test data
# Version: 18.0
1F44D                                      ; fully-qualified     # 👍
1F636 200D 1F32B                            ; minimally-qualified # 😶‍🌫
1F44D 1F44D                                  ; unqualified         # 👍👍
1F3FD                                      ; component           # 🏽
"""

    assert emoji_generator.parse_emoji_test(fixture) == [
        "1F44D",
        "1F636 200D 1F32B",
    ]


def test_unicode_generator_rejects_wrong_version_and_invalid_scalars() -> None:
    with pytest.raises(ValueError, match="version mismatch"):
        emoji_generator.parse_emoji_test("# Version: 15.1\n1F44D; fully-qualified # 👍")

    with pytest.raises(ValueError, match="invalid code point"):
        emoji_generator.parse_emoji_test(
            "# Version: 18.0\nD800; fully-qualified # invalid"
        )

    with pytest.raises(ValueError, match="no qualified sequences"):
        emoji_generator.parse_emoji_test(
            "# Version: 18.0\n1F3FD; component # skin tone"
        )


def test_unicode_generator_checks_source_digest_and_writes_deterministic_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = (
        "# Version: 18.0\n1F44D; fully-qualified # 👍\n2764 FE0F; fully-qualified # ❤️\n"
    ).encode()
    source_path = tmp_path / "emoji-test.txt"
    output_path = tmp_path / "qualified-sequences.txt"
    source_path.write_bytes(fixture)
    monkeypatch.setattr(emoji_generator, "SOURCE_SHA256", sha256(fixture).hexdigest())

    emoji_generator.generate_file(source_path, output_path)

    assert output_path.read_bytes() == b"1F44D\n2764 FE0F\n"
    monkeypatch.setattr(emoji_generator, "SOURCE_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="checksum mismatch"):
        emoji_generator.generate_file(source_path, output_path)
    assert output_path.read_bytes() == b"1F44D\n2764 FE0F\n"


def test_unicode_generator_main_writes_deterministic_rows_without_changing_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = (
        b"# Version: 18.0\n"
        b"1F44D; fully-qualified # thumbs up\n"
        b"2764 FE0F; fully-qualified # heart\n"
    )
    source_path = tmp_path / "emoji-test.txt"
    output_path = tmp_path / "generated" / "qualified-sequences.txt"
    source_path.write_bytes(fixture)
    monkeypatch.setattr(emoji_generator, "SOURCE_SHA256", sha256(fixture).hexdigest())
    monkeypatch.setattr(
        sys, "argv", ["generate.py", str(source_path), str(output_path)]
    )

    emoji_generator.main()

    assert output_path.read_bytes() == b"1F44D\n2764 FE0F\n"
    assert source_path.read_bytes() == fixture


def test_unicode_generator_entrypoint_keeps_pinned_digest_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = b"# Version: 18.0\n1F44D; fully-qualified # thumbs up\n"
    source_path = tmp_path / "emoji-test.txt"
    output_path = tmp_path / "generated" / "qualified-sequences.txt"
    source_path.write_bytes(fixture)
    monkeypatch.setattr(
        sys, "argv", ["generate.py", str(source_path), str(output_path)]
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        runpy.run_path(str(Path(emoji_generator.__file__)), run_name="__main__")

    assert source_path.read_bytes() == fixture
    assert not output_path.exists()
    assert not output_path.parent.exists()


def test_bundled_reaction_data_fails_closed_on_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.schemas.chat as chat_schema
    from app.schemas.chat import _load_reaction_emoji_sequences

    monkeypatch.setattr(chat_schema, "_REACTION_EMOJI_DATA_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="integrity check"):
        _load_reaction_emoji_sequences()


@pytest.mark.asyncio
async def test_reaction_creation_is_strict_but_legacy_lookup_and_delete_remain() -> (
    None
):
    maintenance = AsyncMock(spec=ChatMaintenanceService)
    query_service = AsyncMock(spec=ChatQueryService)
    query_service.get_reactors.return_value = []
    user = SimpleNamespace(id=uuid.UUID(CHAT_ID))
    test_app = build_dishka_app(
        router,
        ChatMaintenanceService=maintenance,
        ChatQueryService=query_service,
    )
    test_app.dependency_overrides[get_current_user_from_dishka] = lambda: user
    test_app.dependency_overrides[get_locale] = lambda: "en"
    reaction_path = f"/chats/{CHAT_ID}/messages/{MESSAGE_ID}/reactions"

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://testserver"
    ) as client:
        invalid_post = await client.post(reaction_path, data={"emoji": "legacy"})
        legacy_delete = await client.delete(reaction_path, params={"emoji": "legacy"})
        legacy_lookup = await client.get(reaction_path, params={"emoji": "legacy"})
        valid_responses = (
            await client.post(reaction_path, data={"emoji": "👩🏽‍💻"}),
            await client.delete(reaction_path, params={"emoji": "👩🏽‍💻"}),
            await client.get(reaction_path, params={"emoji": "👩🏽‍💻"}),
        )

    assert invalid_post.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert legacy_delete.status_code == status.HTTP_200_OK
    assert legacy_lookup.status_code == status.HTTP_200_OK
    assert [response.status_code for response in valid_responses] == [
        status.HTTP_200_OK,
        status.HTTP_200_OK,
        status.HTTP_200_OK,
    ]
    maintenance.add_reaction.assert_awaited_once_with(
        uuid.UUID(CHAT_ID), uuid.UUID(MESSAGE_ID), user, "👩🏽‍💻", locale="en"
    )
    assert len(maintenance.remove_reaction.await_args_list) == 2
    assert [call.args[3] for call in maintenance.remove_reaction.await_args_list] == [
        "legacy",
        "👩🏽‍💻",
    ]
    assert len(query_service.get_reactors.await_args_list) == 2
    assert [call.args[2] for call in query_service.get_reactors.await_args_list] == [
        "legacy",
        "👩🏽‍💻",
    ]
