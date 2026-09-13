"""Fail-closed contracts for the BE-04 route dependency inventory."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_route_dependency_inventory import (
    build_inventory,
    check_inventory,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_app(root: Path) -> Path:
    app = root / "app"
    _write(app / "__init__.py", "")
    _write(app / "api" / "__init__.py", "")
    _write(app / "api" / "internal" / "__init__.py", "")
    _write(
        app / "core" / "database.py",
        """
async def get_db():
    yield object()
""",
    )
    _write(
        app / "api" / "deps.py",
        """
from typing import Annotated
from fastapi import Depends
from dishka.integrations.fastapi import FromDishka
from app.core.database import get_db

def get_legacy_service(db=Depends(get_db)):
    return db

def get_current_user_from_dishka(db: FromDishka[object]):
    return db
""",
    )
    _write(
        app / "api" / "routes.py",
        """
from fastapi import APIRouter, Depends
from dishka.integrations.fastapi import FromDishka, inject
from app.api.deps import get_current_user_from_dishka, get_legacy_service

router = APIRouter()

@router.get("/public")
async def public_route():
    return {"ok": True}

@router.websocket("/socket")
async def websocket_worker(websocket):
    return websocket

@router.post("/legacy")
async def legacy_route(service=Depends(get_legacy_service)):
    return service

@router.post("/canonical")
@inject
async def canonical_route(
    service: FromDishka[object],
    user=Depends(get_current_user_from_dishka),
):
    return service, user
""",
    )
    _write(
        app / "api" / "internal" / "worker.py",
        """
from fastapi import APIRouter

router = APIRouter()

@router.post("/callback")
async def worker_callback():
    return {"ok": True}
""",
    )
    return app


def test_inventory_classifies_route_ownership_deterministically(tmp_path: Path) -> None:
    app = _fixture_app(tmp_path)

    first = build_inventory(app)
    second = build_inventory(app)

    assert first == second
    assert [(route["id"], route["ownership"]) for route in first["routes"]] == [
        ("app.api.internal.worker:worker_callback:POST:/callback", "worker_internal"),
        ("app.api.routes:canonical_route:POST:/canonical", "canonical_dishka"),
        ("app.api.routes:legacy_route:POST:/legacy", "approved_legacy"),
        ("app.api.routes:public_route:GET:/public", "public_no_db"),
        ("app.api.routes:websocket_worker:WEBSOCKET:/socket", "worker_internal"),
    ]
    assert first["summary"] == {
        "approved_legacy": 1,
        "canonical_dishka": 1,
        "public_no_db": 1,
        "worker_internal": 2,
    }


def test_check_rejects_new_legacy_route_without_ledger_update(tmp_path: Path) -> None:
    app = _fixture_app(tmp_path)
    ledger = tmp_path / "route-dependency-inventory.json"
    inventory = build_inventory(app)
    inventory["routes"] = [
        route
        for route in inventory["routes"]
        if route["ownership"] != "approved_legacy"
    ]
    inventory["summary"]["approved_legacy"] = 0
    ledger.write_text(json.dumps(inventory), encoding="utf-8")

    violations = check_inventory(app, ledger)

    assert violations == [
        "route dependency inventory drift: added "
        "app.api.routes:legacy_route:POST:/legacy (approved_legacy)"
    ]


def test_check_rejects_mixed_session_ownership_even_when_ledger_matches(
    tmp_path: Path,
) -> None:
    app = _fixture_app(tmp_path)
    route_file = app / "api" / "routes.py"
    route_file.write_text(
        route_file.read_text(encoding="utf-8")
        + """

@router.post("/mixed")
@inject
async def mixed_route(
    service: FromDishka[object],
    legacy=Depends(get_legacy_service),
):
    return service, legacy
""",
        encoding="utf-8",
    )
    ledger = tmp_path / "route-dependency-inventory.json"
    ledger.write_text(
        json.dumps(build_inventory(app), sort_keys=True),
        encoding="utf-8",
    )

    violations = check_inventory(app, ledger)

    assert violations == [
        "mixed route dependency ownership is forbidden: "
        "app.api.routes:mixed_route:POST:/mixed"
    ]


def test_repository_route_dependency_inventory_is_current_and_has_no_mixed_owner() -> (
    None
):
    violations = check_inventory(
        REPO_ROOT / "app",
        REPO_ROOT / "quality" / "route-dependency-inventory.json",
    )

    assert violations == []
