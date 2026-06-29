import pytest
import binascii
from unittest.mock import MagicMock, patch
from app.services.attendance_tokens import verify_token, AttendanceTokenInvalid, AttendanceTokenPayload
from datetime import datetime

def test_verify_token_invalid_structure():
    attendance = MagicMock()
    with pytest.raises(AttendanceTokenInvalid, match="Token structure is invalid"):
        verify_token("invalid_token_no_dot", attendance)

@patch("app.services.attendance_tokens._b64decode")
def test_verify_token_invalid_payload_encoding(mock_b64decode):
    attendance = MagicMock()
    mock_b64decode.side_effect = binascii.Error("invalid base64")
    with pytest.raises(AttendanceTokenInvalid, match="Token payload encoding is invalid"):
        verify_token("invalid_base64***.signature", attendance)

@patch("app.services.attendance_tokens._b64encode")
@patch("app.services.attendance_tokens._b64decode")
def test_verify_token_invalid_signature_encoding(mock_b64decode, mock_b64encode):
    attendance = MagicMock()
    
    # Let the payload pass decode
    def side_effect(val):
        if val == "payload":
            return b"payload"
        if val == "invalid_sig***":
            raise binascii.Error("Invalid sig")
        return b""
    mock_b64decode.side_effect = side_effect
    mock_b64encode.return_value = "payload"
    
    with pytest.raises(AttendanceTokenInvalid, match="Token signature encoding is invalid"):
        verify_token("payload.invalid_sig***", attendance)

@patch("app.services.attendance_tokens.hmac.compare_digest", return_value=True)
@patch("app.services.attendance_tokens._b64decode")
@patch("app.services.attendance_tokens._b64encode")
def test_verify_token_invalid_payload_json(mock_encode, mock_decode, mock_compare):
    attendance = MagicMock()
    # Let decoding pass, but json decode fail
    mock_decode.side_effect = lambda x: b"payload" if x == "payload" else b"sig"
    mock_encode.side_effect = lambda x: "payload" if x == b"payload" else "sig"
    
    with pytest.raises(AttendanceTokenInvalid, match="Token payload is invalid"):
        verify_token("payload.sig", attendance)
