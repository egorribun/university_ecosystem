from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def setup_cors(app):
    origins = settings.frontend_origins_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
        allow_headers=["*"],
    )
