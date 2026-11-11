"""Strict origin-response evidence, using offline ZAP API boundary fixtures."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

TARGET = "https://stage.example.test/private"
REQUEST = "GET https://stage.example.test/private HTTP/1.1\r\nHost: stage.example.test\r\n\r\n"
RESPONSE = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n"


def _module():
    spec = importlib.util.find_spec("scripts.quality.zap_origin_evidence")
    assert spec is not None, "missing authorized-origin response verifier"
    return importlib.import_module("scripts.quality.zap_origin_evidence")


def _proof(request: str = REQUEST, response: str = RESPONSE):
    return {
        "schema_version": 1,
        "message_id": "1",
        "request_header": request,
        "response_header": response,
    }


def test_exact_origin_and_real_2xx_response_are_accepted() -> None:
    _module().validate_proof(_proof(), TARGET)


def test_default_port_and_case_normalization_preserve_origin() -> None:
    request = "GET https://STAGE.example.test:443/path HTTP/1.1\r\nHost: stage.example.test:443\r\n\r\n"
    _module().validate_proof(_proof(request), TARGET)


@pytest.mark.parametrize(
    "request_header",
    [
        REQUEST.replace("https:", "http:"),
        REQUEST.replace("stage.example.test", "stage.example.test.attacker.invalid"),
        REQUEST.replace("stage.example.test", "stage.example.test:444"),
        REQUEST.replace("Host: stage.example.test", "Host: attacker.invalid"),
        REQUEST.replace(
            "Host: stage.example.test",
            "Host: stage.example.test\r\nHost: attacker.invalid",
        ),
        REQUEST.replace("GET https://stage.example.test/private", "GET /private"),
        REQUEST.replace(
            "https://stage.example.test", "https://user@stage.example.test"
        ),
        REQUEST.replace(
            "https://stage.example.test",
            "https://stage.example.test%2eattacker.invalid",
        ),
        REQUEST.replace("GET", "CONNECT"),
        REQUEST.replace("\r\n", "\n"),
    ],
)
def test_ambiguous_or_unauthorized_request_is_rejected(request_header: str) -> None:
    with pytest.raises(ValueError):
        _module().validate_proof(_proof(request_header), TARGET)


@pytest.mark.parametrize(
    "response",
    [
        "",
        "HTTP/1.1 502 Bad Gateway\r\n\r\n",
        "HTTP/1.1 504 Gateway Timeout\r\n\r\n",
        "HTTP/1.1 302 Found\r\nLocation: https://attacker.invalid\r\n\r\n",
        "HTTP/1.1 401 Unauthorized\r\n\r\n",
        "HTTP/1.1 100 Continue\r\n\r\n",
        "not HTTP",
        "HTTP/1.1 200 OK\n\n",
    ],
)
def test_no_response_proxy_errors_and_non2xx_do_not_prove_execution(
    response: str,
) -> None:
    with pytest.raises(ValueError):
        _module().validate_proof(_proof(response=response), TARGET)


def test_hook_captures_only_headers_from_zap_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    target, proof = tmp_path / "target", tmp_path / "proof.json"
    target.write_text(TARGET)
    monkeypatch.setattr(module, "TARGET_PATH", target)
    monkeypatch.setattr(module, "PROOF_PATH", proof)

    def messages(*, start, count):
        assert start == 1 and count == 1
        return [
            {
                "id": "1",
                "requestHeader": REQUEST,
                "responseHeader": RESPONSE,
                "responseBody": "private-body-marker",
            }
        ]

    module.zap_pre_shutdown(SimpleNamespace(core=SimpleNamespace(messages=messages)))
    assert json.loads(proof.read_text()) == _proof()
    assert "private-body-marker" not in proof.read_text()


def test_hook_requires_zap_response_not_just_site_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    target, proof = tmp_path / "target", tmp_path / "proof.json"
    target.write_text(TARGET)
    monkeypatch.setattr(module, "TARGET_PATH", target)
    monkeypatch.setattr(module, "PROOF_PATH", proof)
    with pytest.raises(ValueError):
        module.zap_pre_shutdown(
            SimpleNamespace(core=SimpleNamespace(messages=lambda **_: []))
        )
    assert not proof.exists()


def test_hook_does_not_use_raw_prefix_to_select_normalized_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    target, proof = tmp_path / "target", tmp_path / "proof.json"
    target.write_text("https://STAGE.example.test:443/private")
    monkeypatch.setattr(module, "TARGET_PATH", target)
    monkeypatch.setattr(module, "PROOF_PATH", proof)

    def messages(*, start, count, baseurl=None):
        # Model official CoreAPI's raw, case-sensitive URL prefix filter.
        if baseurl and not "https://stage.example.test/private".startswith(baseurl):
            return []
        return [{"id": "1", "requestHeader": REQUEST, "responseHeader": RESPONSE}]

    module.zap_pre_shutdown(SimpleNamespace(core=SimpleNamespace(messages=messages)))
    assert proof.is_file()


def test_hook_uses_one_based_pagination_through_last_bounded_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    target, proof = tmp_path / "target", tmp_path / "proof.json"
    target.write_text(TARGET)
    monkeypatch.setattr(module, "TARGET_PATH", target)
    monkeypatch.setattr(module, "PROOF_PATH", proof)
    monkeypatch.setattr(module, "MAX_MESSAGES", 2)
    records = [
        {
            "id": "1",
            "requestHeader": REQUEST,
            "responseHeader": "HTTP/1.1 502 Bad Gateway\r\n\r\n",
        },
        {"id": "2", "requestHeader": REQUEST, "responseHeader": RESPONSE},
    ]

    def messages(*, start, count, baseurl=None):
        return records[max(1, start) - 1 : max(1, start) - 1 + count]

    module.zap_pre_shutdown(SimpleNamespace(core=SimpleNamespace(messages=messages)))
    assert json.loads(proof.read_text())["message_id"] == "2"


@pytest.mark.parametrize(
    "target",
    [
        None,
        "https://stage.example.test /private",
        "https://user@stage.example.test",
        "ftp://stage.example.test",
    ],
)
def test_invalid_expected_origin_is_rejected(target) -> None:
    with pytest.raises(ValueError):
        _module().validate_proof(_proof(), target)


@pytest.mark.parametrize(
    "header",
    [
        REQUEST.replace("Host:", "Broken Header:"),
        REQUEST.replace("Host:", " Host:"),
        REQUEST.replace("Host:", "Host\x00:"),
        REQUEST.replace("Host:", "Host\x7f:"),
        REQUEST + "x" * 65537,
    ],
)
def test_malformed_headers_are_not_origin_evidence(header: str) -> None:
    with pytest.raises(ValueError):
        _module().validate_proof(_proof(header), TARGET)


@pytest.mark.parametrize(
    "proof",
    [
        [],
        {},
        {**_proof(), "schema_version": True},
        {**_proof(), "message_id": "0"},
        {**_proof(), "message_id": 1},
    ],
)
def test_invalid_proof_shape_is_rejected(proof) -> None:
    with pytest.raises(ValueError):
        _module().validate_proof(proof, TARGET)


@pytest.mark.parametrize(
    "records", [{"error": "no history"}, [{}, {}], ["not an object"]]
)
def test_unexpected_api_shape_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, records
) -> None:
    module = _module()
    target, proof = tmp_path / "target", tmp_path / "proof.json"
    target.write_text(TARGET)
    monkeypatch.setattr(module, "TARGET_PATH", target)
    monkeypatch.setattr(module, "PROOF_PATH", proof)
    with pytest.raises(ValueError):
        module.zap_pre_shutdown(
            SimpleNamespace(core=SimpleNamespace(messages=lambda **_: records))
        )
    assert not proof.exists()


def test_history_search_is_bounded_and_cannot_fall_back_to_site_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    target, proof = tmp_path / "target", tmp_path / "proof.json"
    target.write_text(TARGET)
    monkeypatch.setattr(module, "TARGET_PATH", target)
    monkeypatch.setattr(module, "PROOF_PATH", proof)
    monkeypatch.setattr(module, "MAX_MESSAGES", 2)
    positions = []

    def messages(*, start, count):
        positions.append(start)
        return [{"id": str(start), "requestHeader": REQUEST, "responseHeader": ""}]

    with pytest.raises(ValueError):
        module.zap_pre_shutdown(
            SimpleNamespace(core=SimpleNamespace(messages=messages))
        )
    assert positions == [1, 2]
    assert not proof.exists()
