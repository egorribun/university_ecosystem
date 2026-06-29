from hypothesis import given
from hypothesis import strategies as st

from app.utils.encryption import decrypt, encrypt


@given(st.text())
def test_encryption_roundtrip(data):
    encrypted = encrypt(data)
    decrypted = decrypt(encrypted)
    assert decrypted == data
