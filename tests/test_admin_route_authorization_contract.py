"""Admin-only routes must be gated by the SpiceDB-backed admin dependency.

The local ``user.role`` column must never be the sole gate for a privileged
operation (see ``PermissionChecker.check_admin``), so every admin-only route
depends on ``get_current_admin_user_from_dishka`` instead of an inline role
comparison. The check reads the committed AST route inventory, which the
route-dependency gate keeps in sync with the handlers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

INVENTORY = (
    Path(__file__).resolve().parents[1] / "quality" / "route-dependency-inventory.json"
)
ADMIN_GATE = "app.api.deps.auth.get_current_admin_user_from_dishka"

ADMIN_ONLY_ROUTE_IDS = [
    "app.api.users:create_user:POST:",
    "app.api.chat:clear_chat_history:POST:/{chat_id}/clear",
    "app.api.chat:delete_chat:DELETE:/{chat_id}",
    "app.api.news:create_news:POST:",
    "app.api.news:update_news:PATCH:/{id}",
    "app.api.news:delete_news:DELETE:/{id}",
    "app.api.news:upload_news_image:POST:/upload_image",
    "app.api.stories:create_story:POST:",
    "app.api.stories:update_story:PATCH:/{story_id}",
    "app.api.stories:delete_story:DELETE:/{story_id}",
    "app.api.stories:upload_story_cover:POST:/upload_cover",
    "app.api.users:export_access_audit:GET:/audit/export",
    "app.routers.notifications:send_test:POST:/test",
    "app.routers.notifications:broadcast:POST:/broadcast",
    "app.routers.notifications:announce_platform_release:POST:/admin/releases",
    "app.routers.notifications:disable_user_push:POST:/admin/disable-user",
    "app.routers.notifications:admin_get_user_topics:GET:/admin/topics/{user_id}",
    "app.routers.notifications:admin_update_user_topics:PUT:/admin/topics/{user_id}",
]


def _dependencies_by_route() -> dict[str, list[str]]:
    routes = json.loads(INVENTORY.read_text(encoding="utf-8"))["routes"]
    return {route["id"]: route["dishka_dependencies"] for route in routes}


@pytest.mark.parametrize("route_id", ADMIN_ONLY_ROUTE_IDS)
def test_admin_only_route_depends_on_spicedb_admin_gate(route_id: str) -> None:
    dependencies = _dependencies_by_route()
    assert route_id in dependencies, f"{route_id} missing from the route inventory"
    assert ADMIN_GATE in dependencies[route_id]
