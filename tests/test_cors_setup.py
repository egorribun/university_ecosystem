from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cors_setup import setup_cors


def test_setup_cors_adds_middleware():
    app = FastAPI()

    # Check if CORSMiddleware is present before
    initial_middleware_count = len(app.user_middleware)

    setup_cors(app)

    # Check if middleware was added
    assert len(app.user_middleware) == initial_middleware_count + 1

    # Verify it's CORSMiddleware
    middleware = app.user_middleware[0]
    # In Starlette, it's middleware.cls
    assert middleware.cls == CORSMiddleware

    # Verify some kwargs are present in middleware.kwargs
    assert "allow_origins" in middleware.kwargs
    assert "allow_methods" in middleware.kwargs
