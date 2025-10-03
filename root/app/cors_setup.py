from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def setup_cors(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=settings.cors_allow_credentials_effective,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
        expose_headers=settings.cors_expose_headers_list,
    )
