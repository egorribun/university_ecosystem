from __future__ import annotations

# Configure uvloop before any other asyncio usage for optimal async performance
from app.core.uvloop_setup import configure_uvloop

configure_uvloop()

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from fastapi.responses import JSONResponse, ORJSONResponse
except ImportError:
    from fastapi.responses import JSONResponse

    ORJSONResponse = JSONResponse  # type: ignore[misc,assignment]
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_api_router
from app.api.health import router as health_router
from app.api.internal import router as internal_api_router
from app.api.public import router as public_api_router
from app.api.websocket import router as websocket_router
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import AppException, app_exception_handler
from app.core.exceptions.domain import DomainException
from app.core.exceptions.handlers import (
    domain_exception_handler,
    http_exception_handler,
)
from app.core.lifespan import lifespan
from app.core.metrics import configure_metrics
from app.core.middleware import (
    _ensure_vary_header,  # noqa: F401 - re-exported for API modules
    configure_middleware,
)
from app.core.observability import configure_observability
from app.core.versioning import API_VERSION
from app.graphql.schema import graphql_router
from app.services.file_scanner import (
    scan_for_malware as _scan_for_malware,
)

# Re-exports for test compatibility and internal use
scan_for_malware = _scan_for_malware

# Initialize Pyroscope
if os.getenv("ENABLE_PROFILING", "false").lower() == "true":
    try:
        import pyroscope

        pyroscope.configure(
            application_name="university-backend",
            server_address=os.getenv(
                "PYROSCOPE_SERVER_ADDRESS", "http://pyroscope:4040"
            ),
        )
        logging.info("Pyroscope continuous profiling enabled.")
    except ImportError:
        logging.warning(
            "Pyroscope is enabled via ENABLE_PROFILING but the 'pyroscope-io' package is not installed."
        )
    except Exception as e:
        logging.error(f"Failed to initialize Pyroscope: {e}")

# Disable interactive API documentation in non-development environments to
# reduce attack surface (schema enumeration, PoC generation by attackers).
_is_dev = settings.environment in {"development", "testing", "local"}
app = FastAPI(
    title="University Ecosystem API",
    description=(
        "REST API for university life management platform - "
        "schedules, news, events, notifications, and more."
    ),
    version=API_VERSION,
    default_response_class=ORJSONResponse,
    docs_url="/api/docs" if _is_dev else None,
    redoc_url="/api/redoc" if _is_dev else None,
    openapi_url="/api/openapi.json" if _is_dev else None,
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]

# Observability & Metrics
configure_observability(app, engine=engine)
configure_metrics(app)

# Middlewares
configure_middleware(app, settings=settings)


class ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose body exceeds MAX_BODY bytes.

    Defence-in-depth layer on top of any upstream proxy limits (nginx/caddy).
    Handles both Content-Length declared and chunked Transfer-Encoding requests
    so that attackers cannot bypass the check by omitting the header.
    """

    MAX_BODY: int = 5 * 1024 * 1024  # 5 MB — configurable via settings override
    _OVERSIZED = JSONResponse(status_code=413, content={"detail": "Payload Too Large"})
    _BAD_CL = JSONResponse(
        status_code=400, content={"detail": "Invalid Content-Length header"}
    )

    async def dispatch(self, request: Request, call_next):
        limit = getattr(settings, "max_upload_body_bytes", self.MAX_BODY)

        # Fast path: Content-Length declared → reject immediately, no body read.
        cl_header = request.headers.get("content-length")
        if cl_header is not None:
            try:
                cl = int(cl_header)
            except ValueError:
                return self._BAD_CL
            if cl > limit:
                return self._oversized_response(limit)

        # Slow path: chunked / unknown length — stream and accumulate byte count.
        # Only applies to non-WebSocket HTTP requests with a body.
        method = request.method.upper()
        path = request.url.path or ""
        has_body = method in {"POST", "PUT", "PATCH"} and not path.startswith("/ws")
        if has_body and cl_header is None:
            accumulated = 0
            async for chunk in request.stream():
                accumulated += len(chunk)
                if accumulated > limit:
                    return self._oversized_response(limit)

        return await call_next(request)

    @staticmethod
    def _oversized_response(limit: int) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Payload Too Large (max {limit // (1024 * 1024)} MB)"},
        )


app.add_middleware(ContentSizeLimitMiddleware)

# Static files
static_dir = settings.static_dir_path
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

_logger = logging.getLogger(__name__)


@app.get("/", response_class=JSONResponse, summary="Root")
async def get_root():
    return JSONResponse(status_code=200, content={"status": "ok"})


# Routers
app.include_router(health_router)
app.include_router(public_api_router)
app.include_router(admin_api_router, include_in_schema=True)
app.include_router(internal_api_router, include_in_schema=False)
app.include_router(websocket_router)
app.include_router(graphql_router, prefix="/graphql", include_in_schema=False)
