from __future__ import annotations

from functools import cached_property
from pathlib import Path


from pydantic import AliasChoices, Field, field_validator

from .base import _PROJECT_ROOT, BaseAppSettings, _coerce_int_list


class StorageSettings(BaseAppSettings):
    storage_backend: str = "static"
    health_storage_probe_enabled: bool = True

    storage_static_base_url: str = "/static"
    storage_s3_bucket: str = ""
    storage_s3_region: str = ""
    storage_s3_access_key_id: str = ""
    storage_s3_secret_access_key: str = ""
    storage_s3_endpoint_url: str = ""
    storage_s3_base_url: str = ""

    static_dir: str = "app/static"
    image_max_width: int = 1920
    image_max_height: int = 1920
    response_compression_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "response_compression_enabled", "enable_response_compression"
        ),
    )

    image_proxy_enabled: bool = True
    image_proxy_cache_dir: str = "cache/images"
    image_proxy_cache_size_gb: float = 2.0
    image_proxy_allowed_widths: str | list[int] = "100,200,400,800,1200,1600"

    event_file_allowed_mime_types: str | list[str] = (
        "application/pdf,"
        "text/plain,"
        "application/msword,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.ms-excel,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    event_file_allowed_extensions: str | list[str] = ".pdf,.txt,.doc,.docx,.xls,.xlsx"
    event_file_max_size_bytes: int = 10 * 1024 * 1024
    event_file_scanner_enabled: bool = False
    event_file_scanner_backend: str = "clamd"
    event_file_scanner_host: str = "127.0.0.1"
    event_file_scanner_port: int = 3310
    event_file_scanner_socket: str = ""
    event_file_scanner_timeout: float = 30.0
    event_file_scanner_max_size_mb: float = Field(default=25.0, ge=0.0)
    event_file_scanner_max_duration_sec: float = Field(default=10.0, ge=0.0)

    chat_attachment_allowed_mime_types: str | list[str] = (
        "image/jpeg,image/png,image/webp,image/gif,"
        "video/mp4,video/quicktime,"
        "application/pdf,text/plain"
    )
    chat_attachment_allowed_extensions: str | list[str] = (
        ".jpg,.jpeg,.png,.webp,.gif,.mp4,.mov,.pdf,.txt"
    )
    chat_attachment_max_size_bytes: int = 15 * 1024 * 1024
    chat_attachment_max_files: int = 5

    @cached_property
    def chat_attachment_allowed_mime_types_set(self) -> set[str]:
        return {
            m.strip().lower()
            for m in _coerce_str_list(self.chat_attachment_allowed_mime_types)
            if m.strip()
        }

    @cached_property
    def event_file_allowed_mime_types_set(self) -> set[str]:
        return {
            m.strip().lower()
            for m in _coerce_str_list(self.event_file_allowed_mime_types)
            if m.strip()
        }


    @field_validator("storage_backend")
    @classmethod
    def _validate_storage_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"static", "filesystem", "local", "s3", "minio"}:
            raise ValueError(
                "STORAGE_BACKEND must be one of static, filesystem, local, s3, or minio"
            )
        return normalized

    @field_validator("image_proxy_allowed_widths", mode="before")
    @classmethod
    def _validate_image_proxy_widths(cls, value: str | list[int] | None) -> list[int]:
        return sorted(_coerce_int_list(value))

    @property
    def static_dir_path(self) -> Path:
        raw_path = Path(self.static_dir)
        if not raw_path.is_absolute():
            raw_path = (_PROJECT_ROOT / raw_path).resolve()
        return raw_path
