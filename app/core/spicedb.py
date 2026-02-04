from __future__ import annotations

import logging
from functools import lru_cache

from authzed.api.v1 import Client

from app.core.config import settings

logger = logging.getLogger(__name__)


class SpiceDBClient:
    """
    SpiceDB client wrapper using authzed-python.
    Handles connection lifecycle and provides access to the API.
    """

    def __init__(self) -> None:
        self.client: Client | None = None
        self._token = settings.spicedb_preshared_key
        self._endpoint = settings.spicedb_endpoint

    def _init_client(self) -> Client:
        if self.client:
            return self.client

        if not self._token:
            logger.warning(
                "SPICEDB_PRESHARED_KEY is not set. SpiceDB integration will fail."
            )

        # In production, we should use TLS. For this ecosystem, we assume internal gRPC.
        # But we align with 2026 best practices: support for secure channels.
        use_ssl = self._endpoint.startswith("https://") or "443" in self._endpoint

        # Clean endpoint
        endpoint = self._endpoint.replace("http://", "").replace("https://", "")

        if use_ssl:
            from grpcutil import bearer_token_credentials

            self.client = Client(
                target=endpoint,
                credentials=bearer_token_credentials(self._token),
            )
        else:
            from authzed.api.v1 import InsecureClient

            self.client = InsecureClient(
                target=endpoint,
                token=self._token,
            )
        return self.client

    def get_client(self) -> Client:
        return self._init_client()


@lru_cache
def get_spicedb_client() -> Client:
    """Singleton provider for SpiceDB client."""
    return SpiceDBClient().get_client()
