import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_static_file_served_with_cache_control(root_client):
    avatars_dir = settings.static_dir_path / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    file_path = avatars_dir / "demo.txt"
    file_path.write_text("demo", encoding="utf-8")

    response = await root_client.get("/static/avatars/demo.txt")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/plain")
    cache_control = response.headers.get("cache-control", "")
    assert "max-age=" in cache_control.lower()
    assert "public" in cache_control.lower()
    assert "immutable" not in cache_control.lower()

    file_path.unlink(missing_ok=True)
    # Leave directories in place for other tests.


@pytest.mark.asyncio
async def test_private_attachment_static_paths_are_not_public(root_client):
    private_dir = settings.static_dir_path / "chat_uploads" / "chat_test"
    private_dir.mkdir(parents=True, exist_ok=True)
    file_path = private_dir / "secret.txt"
    file_path.write_text("secret", encoding="utf-8")
    try:
        response = await root_client.get("/static/chat_uploads/chat_test/secret.txt")
        head = await root_client.head("/static/chat_uploads/chat_test/secret.txt")
        assert response.status_code == 404
        assert head.status_code == 404
        assert "public" not in response.headers.get("cache-control", "").lower()
    finally:
        file_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_quarantined_upload_is_not_public_static_content(root_client):
    quarantine_dir = settings.static_dir_path / "quarantine" / "news_images"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    file_path = quarantine_dir / "rejected.bin"
    file_path.write_bytes(b"rejected-upload")
    try:
        for method in (root_client.get, root_client.head):
            response = await method("/static/quarantine/news_images/rejected.bin")
            assert response.status_code == 404
            assert response.headers.get("cache-control") == "no-store"
    finally:
        file_path.unlink(missing_ok=True)
