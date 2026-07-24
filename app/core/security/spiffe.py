"""SPIFFE Workload API Integration & mTLS Security Layer.

Provides SVIDManager for dynamic X.509 certificate auto-rotation over SPIRE agent
Unix domain socket, server/client SSLContext builders, ASGI middleware for peer
SPIFFE ID validation, and helper credentials for outbound gRPC/HTTP channels.
"""

from __future__ import annotations

import atexit
import os
import shutil
import ssl
import tempfile
import threading
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.logging import get_logger

_logger = get_logger(__name__)

try:
    from pyspiffe.spiffe_id.spiffe_id import SpiffeId  # type: ignore[import-not-found]
    from pyspiffe.workloadapi.x509_source import (  # type: ignore[import-not-found]
        X509Source,
    )

    _PYSPIFFE_AVAILABLE = True
except ImportError:
    _PYSPIFFE_AVAILABLE = False
    SpiffeId = None
    X509Source = None


def _load_cert_chain_from_pem(
    context: ssl.SSLContext,
    cert_pem: bytes,
    key_pem: bytes,
    lock: threading.Lock | threading.RLock | None = None,
    svid_manager: SVIDManager | None = None,
) -> None:
    """Load PEM certificate and private key bytes into an SSLContext using managed active SVID files under lock."""

    def _do_load() -> None:
        mgr = svid_manager or globals().get("svid_manager")
        if mgr is not None and isinstance(mgr, SVIDManager):
            cert_file, key_file = mgr._write_active_files((cert_pem, key_pem))
            context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        else:
            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as cert_f:
                cert_f.write(cert_pem)
                cert_f.flush()
                cert_tmp = cert_f.name
            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as key_f:
                key_f.write(key_pem)
                key_f.flush()
                key_tmp = key_f.name
            try:
                context.load_cert_chain(certfile=cert_tmp, keyfile=key_tmp)
            finally:
                try:
                    if os.path.exists(cert_tmp):
                        os.unlink(cert_tmp)
                except (FileNotFoundError, OSError):  # RZ-20-04
                    pass
                try:
                    if os.path.exists(key_tmp):
                        os.unlink(key_tmp)
                except (FileNotFoundError, OSError):  # RZ-20-04
                    pass

    if lock is not None:
        with lock:
            _do_load()
    else:
        _do_load()


class SVIDManager:
    """Manages the SPIFFE Workload API connection and dynamic X.509 SVID rotation with managed active files."""

    def __init__(
        self,
        socket_path: str = "/tmp/spire-agent/public/api.sock",  # noqa: S108
        spiffe_id: str = "spiffe://university.ecosystem/ns/default/sa/app",
        enabled: bool = False,
    ) -> None:
        self.socket_path = socket_path
        self.spiffe_id_str = spiffe_id
        self.enabled = enabled
        self._source: Any = None
        self._cached_pair: tuple[bytes, bytes] | None = None
        self._server_ssl_context: ssl.SSLContext | None = None
        self._client_ssl_context: ssl.SSLContext | None = None
        self._last_loaded_pair: tuple[bytes, bytes] | None = None
        self._last_written_pair: tuple[bytes, bytes] | None = None
        self._lock = threading.RLock()

        self._temp_dir: str = tempfile.mkdtemp(prefix="spiffe_svid_")
        self._active_cert_file: str = os.path.join(self._temp_dir, "svid_active.crt")
        self._active_key_file: str = os.path.join(self._temp_dir, "svid_active.key")
        atexit.register(self.close)

    def close(self) -> None:
        """Clean up managed temporary directory and resources."""
        with self._lock:
            if hasattr(self, "_temp_dir") and self._temp_dir and os.path.exists(self._temp_dir):
                try:
                    shutil.rmtree(self._temp_dir, ignore_errors=True)
                except Exception as exc:  # RZ-22-01-JUSTIFIED: temp dir cleanup error ignored during shutdown
                    _logger.debug("Failed to clean up SPIFFE temp dir: %s", exc)
                self._temp_dir = ""

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: S110 # RZ-22-01-JUSTIFIED: destructor exception suppressed
            pass

    def _write_active_files(self, pair: tuple[bytes, bytes]) -> tuple[str, str]:
        """Write active SVID PEM pair to managed active files under lock."""
        with self._lock:
            if not self._temp_dir or not os.path.exists(self._temp_dir):
                self._temp_dir = tempfile.mkdtemp(prefix="spiffe_svid_")
                self._active_cert_file = os.path.join(self._temp_dir, "svid_active.crt")
                self._active_key_file = os.path.join(self._temp_dir, "svid_active.key")
                self._last_written_pair = None

            if pair != self._last_written_pair or not (
                os.path.exists(self._active_cert_file) and os.path.exists(self._active_key_file)
            ):
                cert_pem, key_pem = pair
                with open(self._active_cert_file, "wb") as f_cert:
                    f_cert.write(cert_pem)
                    f_cert.flush()
                with open(self._active_key_file, "wb") as f_key:
                    f_key.write(key_pem)
                    f_key.flush()
                self._last_written_pair = pair
            return self._active_cert_file, self._active_key_file

    def start(self) -> None:
        """Initialize the X509Source background watcher if enabled."""
        if not self.enabled:
            _logger.info("SPIFFE SVIDManager is disabled via configuration.")
            return

        if not _PYSPIFFE_AVAILABLE:
            _logger.warning(
                "pyspiffe is not installed; SPIFFE SVIDManager running in degraded mode."
            )
            return

        try:
            with self._lock:
                self._source = X509Source(socket_path=self.socket_path)
            _logger.info(
                "SPIFFE SVIDManager started successfully. Socket=%s, SPIFFE_ID=%s",
                self.socket_path,
                self.spiffe_id_str,
            )
        except Exception as exc:  # RZ-22-01-JUSTIFIED: SPIFFE watcher init failure logged & handled
            _logger.error("Failed to start SPIFFE SVIDManager watcher: %s", exc)

    def stop(self) -> None:
        """Cleanly close the SPIFFE Workload API watcher."""
        with self._lock:
            if self._source:
                try:
                    self._source.close()
                except Exception as exc:  # RZ-22-01-JUSTIFIED: SPIFFE watcher close failure logged
                    _logger.warning("Error closing SPIFFE X509Source: %s", exc)
                self._source = None
                _logger.info("SPIFFE SVIDManager stopped.")
            self.close()

    def set_active_svid(self, svid: Any = None) -> tuple[bytes, bytes] | None:
        """Set active SVID PEM pair and rebuild internal cached _server_ssl_context and _client_ssl_context under lock."""
        with self._lock:
            if svid is not None:
                if isinstance(svid, tuple) and len(svid) == 2:
                    self._cached_pair = svid
                elif hasattr(svid, "cert_bytes") and hasattr(svid, "private_key_bytes"):
                    self._cached_pair = (svid.cert_bytes, svid.private_key_bytes)
            pair = self.get_active_svid()
            if pair:
                self._write_active_files(pair)
                self._server_ssl_context = create_spiffe_server_ssl_context(self)
                self._client_ssl_context = create_spiffe_client_ssl_context(self)
                self._last_loaded_pair = pair
            return pair

    def get_svid_pem_pair(self) -> tuple[bytes, bytes] | None:
        """Return (cert_chain_pem, private_key_pem) of current active SVID under lock."""
        with self._lock:
            if self._cached_pair:
                return self._cached_pair
            if not self._source:
                return None
            try:
                svid = self._source.get_s_v_i_d()
                if not svid:
                    return None
                return svid.cert_bytes, svid.private_key_bytes
            except Exception as exc:  # RZ-22-01-JUSTIFIED: SVID retrieval error handled
                _logger.warning("Error retrieving SVID from X509Source: %s", exc)
                return None

    def get_active_svid(self) -> tuple[bytes, bytes] | None:
        """Return current active SVID PEM pair (cert_chain_pem, private_key_pem) under lock."""
        return self.get_svid_pem_pair()

    def get_trust_bundle_pem(self) -> bytes | None:
        """Return CA trust bundle PEM bytes under lock."""
        with self._lock:
            if not self._source:
                return None
            try:
                if SpiffeId and self.spiffe_id_str:
                    parsed_id = SpiffeId.parse(self.spiffe_id_str)
                    bundle = self._source.get_bundle_for_trust_domain(
                        parsed_id.trust_domain
                    )
                    if (
                        bundle
                        and hasattr(bundle, "x509_certs_bytes")
                        and isinstance(bundle.x509_certs_bytes, bytes)
                    ):
                        return bundle.x509_certs_bytes
                elif hasattr(self._source, "get_bundle_for_trust_domain"):
                    domain = (
                        self.spiffe_id_str.split("/")[2]
                        if "://" in self.spiffe_id_str
                        else "university.ecosystem"
                    )
                    bundle = self._source.get_bundle_for_trust_domain(domain)
                    if (
                        bundle
                        and hasattr(bundle, "x509_certs_bytes")
                        and isinstance(bundle.x509_certs_bytes, bytes)
                    ):
                        return bundle.x509_certs_bytes
            except Exception as exc:  # RZ-22-01-JUSTIFIED: Trust bundle retrieval error handled
                _logger.warning("Error retrieving trust bundle from X509Source: %s", exc)
                return None
            return None

    def get_server_ssl_context(
        self, allowed_peer_ids: set[str] | None = None
    ) -> ssl.SSLContext:
        """Return up-to-date server SSLContext dynamically loaded with active SVID."""
        with self._lock:
            current_pair = self.get_active_svid()
            if (
                self._server_ssl_context is None
                or current_pair != self._last_loaded_pair
            ):
                self._server_ssl_context = create_spiffe_server_ssl_context(
                    self, allowed_peer_ids
                )
                self._last_loaded_pair = current_pair
            return self._server_ssl_context

    def get_client_ssl_context(
        self, target_spiffe_id: str | None = None
    ) -> ssl.SSLContext:
        """Return up-to-date client SSLContext dynamically loaded with active SVID."""
        with self._lock:
            current_pair = self.get_active_svid()
            if (
                self._client_ssl_context is None
                or current_pair != self._last_loaded_pair
            ):
                self._client_ssl_context = create_spiffe_client_ssl_context(
                    self, target_spiffe_id
                )
                self._last_loaded_pair = current_pair
            return self._client_ssl_context


def create_spiffe_server_ssl_context(
    svid_manager: SVIDManager,
    allowed_peer_ids: set[str] | None = None,
) -> ssl.SSLContext:
    """Create server-side SSLContext enforcing mTLS with SPIFFE ID validation."""
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED

    bundle_pem = svid_manager.get_trust_bundle_pem()
    if bundle_pem:
        context.load_verify_locations(cadata=bundle_pem.decode("utf-8"))

    pair = svid_manager.get_active_svid()
    lock = getattr(svid_manager, "_lock", None)

    if pair:
        cert_pem, key_pem = pair
        _load_cert_chain_from_pem(context, cert_pem, key_pem, lock=lock, svid_manager=svid_manager)
        context._loaded_pair = pair  # type: ignore[attr-defined]

    def _reload_on_sni(ssl_obj: Any, server_name: str | None, ctx: ssl.SSLContext) -> None:
        def _do_reload() -> None:
            current_pair = svid_manager.get_active_svid()
            if current_pair and current_pair != getattr(ctx, "_loaded_pair", None):
                try:
                    fresh_ctx = svid_manager.get_server_ssl_context(allowed_peer_ids)
                    if ctx.verify_mode != ssl.CERT_REQUIRED:
                        fresh_ctx.verify_mode = ctx.verify_mode
                    if ssl_obj is not None and hasattr(ssl_obj, "context"):
                        try:
                            ssl_obj.context = fresh_ctx
                        except (AttributeError, TypeError):
                            pass
                except Exception as exc:  # RZ-22-01-JUSTIFIED: SNI cert reload failure handled
                    _logger.warning(
                        "Failed to dynamically reload SVID cert chain in SNI callback: %s",
                        exc,
                    )

        if lock is not None:
            with lock:
                _do_reload()
        else:
            _do_reload()

    try:
        context.sni_callback = _reload_on_sni  # type: ignore[assignment]
    except (AttributeError, ValueError):
        pass

    return context


def create_spiffe_client_ssl_context(
    svid_manager: SVIDManager,
    target_spiffe_id: str | None = None,
) -> ssl.SSLContext:
    """Create client-side SSLContext for outgoing mTLS HTTP/gRPC requests dynamically initialized with active SVID."""
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED

    bundle_pem = svid_manager.get_trust_bundle_pem()
    if bundle_pem:
        context.load_verify_locations(cadata=bundle_pem.decode("utf-8"))

    pair = svid_manager.get_active_svid()
    lock = getattr(svid_manager, "_lock", None)

    if pair:
        cert_pem, key_pem = pair
        _load_cert_chain_from_pem(context, cert_pem, key_pem, lock=lock, svid_manager=svid_manager)
        context._loaded_pair = pair  # type: ignore[attr-defined]

    return context


class SPIFFEAuthMiddleware:
    """ASGI Middleware verifying client certificate SPIFFE ID on protected endpoints."""

    def __init__(
        self,
        app: ASGIApp,
        allowed_spiffe_ids: set[str] | list[str],
        protected_prefixes: tuple[str, ...] = (
            "/api/internal",
            "/api/v1/chat/check-participant",
        ),
        enabled: bool = True,
    ) -> None:
        self.app = app
        self.allowed_spiffe_ids = set(allowed_spiffe_ids)
        self.protected_prefixes = protected_prefixes
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled:
            await self.app(scope, receive, send)
            return

        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not any(path.startswith(prefix) for prefix in self.protected_prefixes):
            await self.app(scope, receive, send)
            return

        client_spiffe_id = self._extract_spiffe_id(scope)
        if not client_spiffe_id or client_spiffe_id not in self.allowed_spiffe_ids:
            _logger.warning(
                "SPIFFE mTLS authentication failed. Client SPIFFE ID=%s path=%s",
                client_spiffe_id,
                path,
            )
            response = JSONResponse(
                status_code=403,
                content={"detail": "Access denied: untrusted or missing SPIFFE ID"},
            )
            await response(scope, receive, send)
            return

        scope.setdefault("state", {})["spiffe_id"] = client_spiffe_id
        await self.app(scope, receive, send)

    def _extract_spiffe_id(self, scope: Scope) -> str | None:
        """Extract URI SAN SPIFFE ID strictly from transport peercert or SSL context URI SAN."""
        transport = scope.get("transport")
        if transport:
            try:
                peercert = transport.get_extra_info("peercert")
                if peercert and "subjectAltName" in peercert:
                    for san_type, san_val in peercert["subjectAltName"]:
                        if san_type == "URI" and str(san_val).startswith("spiffe://"):
                            return str(san_val)
                ssl_obj = transport.get_extra_info("ssl_object")
                if ssl_obj and hasattr(ssl_obj, "getpeercert"):
                    cert_dict = ssl_obj.getpeercert()
                    if cert_dict and "subjectAltName" in cert_dict:
                        for san_type, san_val in cert_dict["subjectAltName"]:
                            if san_type == "URI" and str(san_val).startswith("spiffe://"):
                                return str(san_val)
            except Exception as exc:  # RZ-22-01-JUSTIFIED: transport info extraction failure handled
                _logger.debug("Failed to extract peercert from transport: %s", exc)

        return None


# Global singleton instance managed by lifespan hooks
svid_manager = SVIDManager()


def get_spiffe_grpc_credentials(manager: SVIDManager | None = None) -> Any | None:
    """Create gRPC ChannelCredentials using active SPIFFE SVID and Trust Bundle."""
    mgr = manager or svid_manager
    if not mgr.enabled:
        return None

    pair = mgr.get_active_svid()
    bundle_pem = mgr.get_trust_bundle_pem()

    if pair and bundle_pem:
        import grpc

        cert_pem, key_pem = pair
        return grpc.ssl_channel_credentials(
            root_certificates=bundle_pem,
            private_key=key_pem,
            certificate_chain=cert_pem,
        )
    return None
