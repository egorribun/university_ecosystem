from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("app.auth.webauthn.metadata")


@dataclass(frozen=True, slots=True)
class MetadataEntry:
    """Summary information for a WebAuthn authenticator."""

    aaguid: str
    description: str | None
    attestation_root_certificates: tuple[str, ...]
    status_reports: tuple[Mapping[str, Any], ...]
    allowed_transports: frozenset[str]
    backup_eligible: bool | None
    trust_score: int
    status_warning: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the metadata."""

        return {
            "aaguid": self.aaguid,
            "description": self.description,
            "attestation_root_certificates": list(self.attestation_root_certificates),
            "status_reports": [dict(report) for report in self.status_reports],
            "allowed_transports": sorted(self.allowed_transports),
            "backup_eligible": self.backup_eligible,
            "trust_score": self.trust_score,
            "status_warning": self.status_warning,
        }


class MetadataLoadError(RuntimeError):
    """Raised when metadata cannot be loaded."""


class WebAuthnMetadataResolver:
    """Resolve metadata for authenticators via the FIDO Metadata Service."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._entries: dict[str, MetadataEntry] = {}
        self._trusted_roots: dict[str, tuple[str, ...]] = {}
        self._fetched_at: float | None = None

    async def get_entry(self, aaguid: str | None) -> MetadataEntry | None:
        if not aaguid:
            return None
        await self._ensure_fresh()
        return self._entries.get(aaguid.lower())

    async def get_trusted_root_certificates(self) -> dict[str, tuple[str, ...]]:
        await self._ensure_fresh()
        return dict(self._trusted_roots)

    async def refresh(self, *, force: bool = False) -> None:
        if not force and not await self._should_refresh():
            return
        async with self._lock:
            if not force and not await self._should_refresh():
                return
            await self._reload()

    def invalidate(self) -> None:
        self._entries.clear()
        self._trusted_roots.clear()
        self._fetched_at = None

    async def _ensure_fresh(self) -> None:
        await self.refresh()

    async def _should_refresh(self) -> bool:
        if not (
            settings.mfa_webauthn_metadata_url or settings.mfa_webauthn_metadata_json
        ):
            if self._entries:
                self.invalidate()
            return False
        if self._fetched_at is None:
            return True
        ttl = max(0, settings.mfa_webauthn_metadata_refresh_seconds)
        if ttl == 0:
            return True
        return (time.time() - self._fetched_at) >= ttl

    async def _reload(self) -> None:
        used_cache = False
        try:
            raw = await self._load_source()
        except Exception as error:  # pragma: no cover - defensive
            if isinstance(error, MetadataLoadError):
                failure = error
            else:
                failure = MetadataLoadError(str(error))
            cached = self._load_cached_payload()
            if cached is not None:
                logger.warning(
                    (
                        "Failed to refresh WebAuthn metadata from source; "
                        "using cached payload (%s)"
                    ),
                    failure,
                    exc_info=True,
                )
                raw = cached
                used_cache = True
            else:
                logger.error(
                    (
                        "Failed to refresh WebAuthn metadata and no cached "
                        "payload is available: %s"
                    ),
                    failure,
                    exc_info=True,
                )
                if self._entries:
                    self._fetched_at = time.time()
                    return
                if failure is error:
                    raise
                raise failure from error
        if raw is None:
            self.invalidate()
            self._clear_cache()
            self._fetched_at = time.time()
            return
        entries = self._parse_entries(raw)
        self._entries = entries
        self._trusted_roots = {
            aaguid: entry.attestation_root_certificates
            for aaguid, entry in entries.items()
        }
        if not used_cache:
            self._persist_cache(raw)
        self._fetched_at = time.time()

    async def _load_source(self) -> Mapping[str, Any] | None:
        json_payload = settings.mfa_webauthn_metadata_json.strip()
        if json_payload:
            try:
                return json.loads(json_payload)
            except json.JSONDecodeError as exc:
                raise MetadataLoadError("Invalid MFA WebAuthn metadata JSON") from exc
        url = settings.mfa_webauthn_metadata_url.strip()
        if not url:
            return {"entries": []}
        timeout = httpx.Timeout(10.0, read=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise MetadataLoadError(
                    f"Failed to download WebAuthn metadata from {url}: {exc}"
                ) from exc
            try:
                return response.json()
            except ValueError as exc:
                raise MetadataLoadError(
                    f"Invalid WebAuthn metadata payload returned by {url}"
                ) from exc

    def _parse_entries(self, raw: Mapping[str, Any]) -> dict[str, MetadataEntry]:
        entries_data = raw.get("entries")
        if not isinstance(entries_data, list):
            return {}
        result: dict[str, MetadataEntry] = {}
        for item in entries_data:
            if not isinstance(item, Mapping):  # pragma: no cover - defensive
                continue
            metadata = self._build_entry(item)
            if metadata:
                result[metadata.aaguid] = metadata
        return result

    def _build_entry(self, payload: Mapping[str, Any]) -> MetadataEntry | None:
        statement = payload.get("metadataStatement")
        if not isinstance(statement, Mapping):
            return None
        aaguid = (payload.get("aaguid") or statement.get("aaguid") or "").strip()
        if not aaguid:
            return None
        aaguid = aaguid.lower()
        description = statement.get("description")
        root_certs = tuple(
            cert
            for cert in statement.get("attestationRootCertificates", [])
            if isinstance(cert, str) and cert.strip()
        )
        status_reports_raw = payload.get("statusReports") or []
        status_reports: list[Mapping[str, Any]] = []
        for report in status_reports_raw:
            if isinstance(report, Mapping):
                status_reports.append(report)
        transports: set[str] = set()
        get_info = statement.get("authenticatorGetInfo")
        if isinstance(get_info, Mapping):
            for transport in get_info.get("transports", []) or []:
                if isinstance(transport, str):
                    transports.add(transport.lower())
        default_transports = statement.get("defaultTransports") or []
        for transport in default_transports:
            if isinstance(transport, str):
                transports.add(transport.lower())
        backup_eligible = statement.get("isBackupEligible")
        if isinstance(backup_eligible, str):
            backup_eligible = backup_eligible.lower() in {"true", "1", "yes"}
        elif not isinstance(backup_eligible, bool):
            backup_eligible = None
        trust_score, status_warning = self._compute_trust_score(status_reports)
        return MetadataEntry(
            aaguid=aaguid,
            description=description if isinstance(description, str) else None,
            attestation_root_certificates=root_certs,
            status_reports=tuple(status_reports),
            allowed_transports=frozenset(transports),
            backup_eligible=backup_eligible,
            trust_score=trust_score,
            status_warning=status_warning,
        )

    def _get_cache_path(self) -> Path | None:
        cache_file = settings.mfa_webauthn_metadata_cache_file.strip()
        if not cache_file:
            return None
        return Path(cache_file).expanduser()

    def _persist_cache(self, payload: Mapping[str, Any]) -> None:
        path = self._get_cache_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(payload, ensure_ascii=False)
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(serialized)
            os.replace(tmp_path, path)
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "Failed to persist WebAuthn metadata cache to %s", path, exc_info=True
            )

    def _clear_cache(self) -> None:
        path = self._get_cache_path()
        if path is None:
            return
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "Failed to remove WebAuthn metadata cache at %s", path, exc_info=True
            )

    def _load_cached_payload(self) -> Mapping[str, Any] | None:
        path = self._get_cache_path()
        if path is None:
            return None
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        except OSError:  # pragma: no cover - defensive
            logger.warning(
                "Unable to stat WebAuthn metadata cache at %s", path, exc_info=True
            )
            return None
        ttl = max(0, settings.mfa_webauthn_metadata_cache_ttl_seconds)
        age = time.time() - stat.st_mtime
        if ttl and age > ttl:
            logger.warning(
                "Cached WebAuthn metadata at %s is stale (age=%d seconds > ttl=%d)",
                path,
                int(age),
                ttl,
            )
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to load cached WebAuthn metadata from %s: %s",
                path,
                exc,
                exc_info=True,
            )
            return None

    def _compute_trust_score(
        self, status_reports: list[Mapping[str, Any]]
    ) -> tuple[int, bool]:
        if not status_reports:
            return (50, False)
        score = 50
        warning = False
        for report in status_reports:
            status = str(report.get("status") or "").upper()
            if not status:
                continue
            if status in {
                "REVOKED",
                "ATTESTATION_KEY_COMPROMISE",
                "USER_VERIFICATION_BYPASS",
                "FIDO_CERTIFIED_WITH_METADATA_L1",
                "CERTIFIED_WITH_METADATA_L1_REVOKED",
                "CERTIFIED_WITH_METADATA_L2_REVOKED",
            }:
                return (0, True)
            if status.startswith("FIDO_CERTIFIED"):
                score = max(score, 100)
            elif status in {"NOT_FIDO_CERTIFIED", "SELF_ASSERTION_SUBMITTED"}:
                score = max(score, 40)
            elif status.endswith("UPDATE_AVAILABLE"):
                warning = True
                score = max(score, 60)
        return (score, warning)


metadata_resolver = WebAuthnMetadataResolver()

__all__ = [
    "MetadataEntry",
    "MetadataLoadError",
    "WebAuthnMetadataResolver",
    "metadata_resolver",
]
