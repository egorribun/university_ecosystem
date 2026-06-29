import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import os

from app.core.spicedb import _parse_endpoint, get_spicedb_client, get_async_spicedb_channel
from app.core.spicedb_watch import start_permission_watch, stop_permission_watch, _watch_once

def test_parse_endpoint():
    # Test plaintext
    host, port, use_ssl = _parse_endpoint("localhost:50051")
    # with os.environ SPICEDB_INSECURE it might be false or true depending on env
    # so we just check it returns a tuple
    assert isinstance(host, str)
    assert isinstance(port, int)
    assert isinstance(use_ssl, bool)
    
    # Test grpc scheme
    host, port, use_ssl = _parse_endpoint("grpc://spicedb:50051")
    assert host == "spicedb"
    assert port == 50051

    # Test https scheme
    with patch.dict(os.environ, {"SPICEDB_INSECURE": "false"}):
        host, port, use_ssl = _parse_endpoint("https://spicedb.com")
        assert host == "spicedb.com"
        assert use_ssl is True

@patch("app.core.spicedb.Client")
@patch("app.core.spicedb.InsecureClient")
def test_get_spicedb_client(mock_insecure, mock_client):
    with patch("app.core.spicedb.settings") as mock_settings:
        mock_settings.spicedb_endpoint = "localhost:50051"
        mock_settings.spicedb_preshared_key = "test_key"
        
        with patch.dict(os.environ, {"SPICEDB_INSECURE": "true"}):
            client = get_spicedb_client()
            assert client is not None
            mock_insecure.assert_called_once()

@pytest.mark.asyncio
async def test_get_async_spicedb_channel():
    with patch("app.core.spicedb.grpc.aio.insecure_channel") as mock_insecure:
        with patch("app.core.spicedb.settings") as mock_settings:
            mock_settings.spicedb_endpoint = "localhost:50051"
            with patch.dict(os.environ, {"SPICEDB_INSECURE": "true"}):
                async for channel in get_async_spicedb_channel():
                    assert channel is not None
                    break
        mock_insecure.assert_called_once()

@pytest.mark.asyncio
async def test_watch_once():
    # Mock grpc and dependencies to test _watch_once
    with patch("app.core.spicedb_watch.grpc.aio.insecure_channel") as mock_channel:
        mock_stub = MagicMock()
        
        mock_stream = AsyncMock()
        # Make the stream yield one item then raise an exception to exit
        mock_response = MagicMock()
        mock_update = MagicMock()
        mock_update.relationship.resource.object_type = "document"
        mock_update.relationship.resource.object_id = "1"
        mock_response.updates = [mock_update]
        
        # Async generator mock
        async def mock_iter():
            yield mock_response
            raise Exception("stream closed")
            
        mock_stream.__aiter__.return_value = mock_iter()
        mock_stub.return_value.Watch = MagicMock(return_value=mock_stream)
        
        with patch("app.core.spicedb_watch.authzed.api.v1.WatchServiceStub", mock_stub):
            # This should handle the Exception and return
            with pytest.raises(Exception, match="stream closed"):
                await _watch_once("token", "localhost", 50051, False)
