import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.utils.encryption import (
    SpotifyEncryptionError,
    _get_cipher,
    decrypt_string,
    encrypt_string,
    reset_cached_cipher,
    rotate_encrypted_string,
)


def test_encryption_roundtrip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()

    original = "secret_data"
    encrypted = encrypt_string(original)
    assert encrypted != original
    decrypted = decrypt_string(encrypted)
    assert decrypted == original


def test_encryption_bytes(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()

    original = b"byte_data"
    encrypted = encrypt_string(original)
    decrypted = decrypt_string(encrypted)
    # decrypt returns string by default decoding utf8
    assert decrypted == "byte_data"


def test_empty_handling():
    assert encrypt_string(None) is None
    assert encrypt_string("") is None
    assert encrypt_string(b"") is None

    assert decrypt_string(None) is None
    assert decrypt_string("") is None
    assert decrypt_string(b"") is None

    assert rotate_encrypted_string(None) is None
    assert rotate_encrypted_string("") is None


def test_rotate_keys(monkeypatch):
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()

    # Encrypt with key2
    monkeypatch.setattr(settings, "spotify_token_secret", key2)
    reset_cached_cipher()
    cipher2 = _get_cipher()
    data = "data"
    token = cipher2.encrypt(data.encode()).decode()

    # Configure multiple keys: key1 is primary, key2 is secondary
    combined = f"{key1},{key2}"
    monkeypatch.setattr(settings, "spotify_token_secret", combined)
    reset_cached_cipher()

    # Decrypt should work (try list)
    decrypted = decrypt_string(token)
    assert decrypted == "data"

    # Rotate should re-encrypt with key1
    rotated = rotate_encrypted_string(token)
    assert rotated != token

    # Verified rotated uses key1
    f1 = Fernet(key1.encode())
    assert f1.decrypt(rotated.encode()).decode() == "data"


def test_invalid_secret_format(monkeypatch):
    monkeypatch.setattr(settings, "spotify_token_secret", "bad_key")
    reset_cached_cipher()
    with pytest.raises(SpotifyEncryptionError):
        _get_cipher()


def test_empty_secret_setting(monkeypatch):
    # If explicitly empty, should fallback to default derive
    monkeypatch.setattr(settings, "spotify_token_secret", "")
    monkeypatch.setattr(settings, "secret_key", "base_secret")
    reset_cached_cipher()

    cipher = _get_cipher()
    assert cipher


def test_no_secret_configured(monkeypatch):
    monkeypatch.setattr(settings, "spotify_token_secret", "")
    monkeypatch.setattr(settings, "secret_key", "")
    reset_cached_cipher()
    with pytest.raises(SpotifyEncryptionError):
        _get_cipher()


def test_decrypt_invalid_token(monkeypatch, caplog):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()

    import logging

    with caplog.at_level(logging.WARNING):
        res = decrypt_string("invalid_token")
        assert res is None
        assert "Failed to decrypt" in caplog.text


def test_empty_secret_entry():
    from app.utils.encryption import _normalize_secret

    with pytest.raises(SpotifyEncryptionError) as exc:
        _normalize_secret("   ")
    assert "SPOTIFY_TOKEN_SECRET contains an empty entry" in str(exc.value)


def test_decrypt_string_bytes(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()
    encrypted = encrypt_string("hello")
    decrypted = decrypt_string(encrypted.encode("utf-8"))
    assert decrypted == "hello"


def test_rotate_single_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()
    token_str = "some_token"
    token_bytes = b"some_token"
    assert rotate_encrypted_string(token_str) == "some_token"
    assert rotate_encrypted_string(token_bytes) == "some_token"


def test_encrypted_string_decorator(monkeypatch):
    from app.utils.encryption import EncryptedString

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()
    decorator = EncryptedString()
    encrypted = decorator.process_bind_param("hello", None)
    assert encrypted != "hello"
    decrypted = decorator.process_result_value(encrypted, None)
    assert decrypted == "hello"


def test_build_cipher_empty():
    from app.utils.encryption import _build_cipher

    with pytest.raises(SpotifyEncryptionError) as exc:
        _build_cipher("")
    assert "SPOTIFY_TOKEN_SECRET is not configured" in str(exc.value)
