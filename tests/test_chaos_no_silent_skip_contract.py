"""AUD-322: opt-in chaos tests fail explicitly; they never skip at runtime."""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from tests.chaos import test_resilience as resilience

CHAOS_RESILIENCE = Path(__file__).resolve().parent / "chaos" / "test_resilience.py"


def _runtime_skips_and_conditional_tests(source: str) -> list[str]:
    tree = ast.parse(source)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in {
            "pytest.skip",
            "pytest.importorskip",
        }:
            findings.append(f"line {node.lineno}: {ast.unparse(node.func)}")
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for decorator in node.decorator_list:
                if "skipif" in ast.unparse(decorator):
                    findings.append(f"line {node.lineno}: skipif on {node.name}")
    return findings


def _client(handler: httpx.MockTransport | None = None) -> httpx.Client:
    return httpx.Client(
        base_url="http://chaos.test",
        transport=handler,
    )


def test_chaos_resilience_has_no_runtime_skip_or_conditional_skip() -> None:
    source = CHAOS_RESILIENCE.read_text(encoding="utf-8")

    assert _runtime_skips_and_conditional_tests(source) == []


def test_runtime_skip_census_detects_skip_calls_and_conditional_decorators() -> None:
    source = (
        "import pytest\n"
        "@pytest.mark.skipif(True, reason='gate')\n"
        "def test_a():\n"
        "    pytest.skip('precondition')\n"
    )

    assert _runtime_skips_and_conditional_tests(source) == [
        "line 3: skipif on test_a",
        "line 4: pytest.skip",
    ]


def test_missing_chat_fails_explicitly_instead_of_skipping() -> None:
    client = _client(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"items": [], "total": 0})
        )
    )
    with client, pytest.raises(pytest.fail.Exception, match="No chat is visible"):
        resilience._first_chaos_chat_id(client)


def test_unauthorized_chaos_chat_lookup_fails_explicitly() -> None:
    client = _client(httpx.MockTransport(lambda request: httpx.Response(401)))
    with client, pytest.raises(pytest.fail.Exception, match="GET returned 401"):
        resilience._first_chaos_chat_id(client)


def test_first_visible_chat_is_returned_as_text() -> None:
    client = _client(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"items": [{"id": 42}]})
        )
    )
    with client:
        assert resilience._first_chaos_chat_id(client) == "42"


def test_unreachable_gateway_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    real_client = httpx.Client

    def refusing_client(**kwargs: object) -> httpx.Client:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        return real_client(transport=httpx.MockTransport(refuse), **kwargs)

    monkeypatch.setattr(resilience.httpx, "Client", refusing_client)

    with pytest.raises(pytest.fail.Exception, match="is unreachable under CHAOS"):
        resilience._require_gateway()


def test_unhealthy_gateway_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    real_client = httpx.Client

    def unhealthy_client(**kwargs: object) -> httpx.Client:
        return real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
            **kwargs,
        )

    monkeypatch.setattr(resilience.httpx, "Client", unhealthy_client)

    with pytest.raises(pytest.fail.Exception, match="returned 503"):
        resilience._require_gateway()


def test_healthy_gateway_passes_the_precondition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.Client

    def healthy_client(**kwargs: object) -> httpx.Client:
        return real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            **kwargs,
        )

    monkeypatch.setattr(resilience.httpx, "Client", healthy_client)

    assert resilience._require_gateway() is None
