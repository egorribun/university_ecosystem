"""Actual Gunicorn entrypoint; workload sources are created only after fork."""

from __future__ import annotations

import asyncio
import os
import sys

from gunicorn.arbiter import Arbiter
from uvicorn.server import Server
from uvicorn_worker import UvicornWorker

from app.server.internal_mtls import load_internal_http_mtls
from app.server.spiffe_identity import WorkloadContexts
from app.server.spiffe_transport import TransportGuard, guarded_protocols


class BackendWorker(UvicornWorker):
    async def _serve(self) -> None:
        policy = load_internal_http_mtls(os.environ)
        if policy is None:
            await super()._serve()
            return
        # _serve runs in the forked worker. Never open gRPC or its background
        # watcher in __init__, at module import or in an application lifespan hook.
        source = WorkloadContexts.connect(policy.socket_path, policy.server_identity)
        guard: TransportGuard | None = None
        try:
            guard = TransportGuard(
                source,
                policy.allowed_clients,
                asyncio.get_running_loop(),
                handshake_diagnostics=os.environ.get("AUD373_TLS_DIAGNOSTICS") == "1",
            )
            context = guard.start()
            http_protocol, ws_protocol = guarded_protocols(guard)
            self.config.app = self.wsgi
            self.config.http = http_protocol
            self.config.ws = ws_protocol
            # The worker exclusively owns TLS: old static-file Gunicorn options
            # must not cause Config.load to instantiate a second stale context.
            self.config.ssl_keyfile = None
            self.config.ssl_certfile = None
            self.config.load()
            self.config.ssl = context
            server = Server(config=self.config)
            self._install_sigquit_handler()
            await server.serve(sockets=self.sockets)
            if not server.started:
                sys.exit(Arbiter.WORKER_BOOT_ERROR)
        finally:
            try:
                if guard is not None:
                    guard.close()
            finally:
                source.close()
