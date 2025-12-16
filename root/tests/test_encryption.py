import pytest
from cryptography.fernet import Fernet
from app.utils.encryption import (
    encrypt_string, decrypt_string, rotate_encrypted_string,
    reset_cached_cipher, SpotifyEncryptionError, _get_cipher
)
from app.core.config import settings

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
