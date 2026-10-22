from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "tests" / "performance" / "ws_hub_mvp_load_test.js"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
WS_HUB_PATH = ROOT / "services" / "ws-hub" / "pkg" / "hub" / "hub.go"


def test_mvp_load_profile_matches_accepted_capacity_and_sla() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    compact = re.sub(r"\s+", "", source)

    expected_profile = {
        "connectionCount": 1000,
        "pairCount": 500,
        "targetMessagesPerSecond": 100,
        "messageIntervalMs": 5000,
        "duration": "30m",
        "deliveryP95Ms": 500,
        "maxConnectionsPerSourceIp": 10,
    }
    for key, value in expected_profile.items():
        if isinstance(value, str):
            assert re.search(rf"\b{key}:\s*['\"]{re.escape(value)}['\"]", source)
        else:
            assert re.search(rf"\b{key}:\s*{value}\b", source)

    assert "minimumSourceIpCount: Math.ceil(1000 / 10)" in source
    assert "rate>=1" in source
    assert "p(95)<=${PROFILE.deliveryP95Ms}" in compact
    assert 'ws_mvp_duplicate_deliveries: ["count==0"]' in source
    assert "count>${PROFILE.minimumMessagesSent-1}" in compact
    assert "count>${PROFILE.minimumMessagesDelivered-1}" in compact
    assert "PROFILE.pairCount*2!==PROFILE.connectionCount" in compact
    assert (
        "(PROFILE.pairCount*1000)/PROFILE.messageIntervalMs!==PROFILE.targetMessagesPerSecond"
        in compact
    )
    assert (
        "PROFILE.pairCount*PROFILE.senderPhaseSpacingMs!==PROFILE.messageIntervalMs"
        in compact
    )
    assert "PROFILE.connectionDurationMs!==30*60*1000" in compact


def test_load_traffic_uses_authorized_chat_api_and_ws_join_only() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    compact = re.sub(r"\s+", "", source)

    assert "/api/v1/chats/${pair.chat_id}/messages" in source
    assert "Idempotency-Key" in source
    assert 'type: "join"' in source
    assert "socket.ping()" in source
    assert "type: 'message'" not in source
    assert "ws.connect(" in source
    assert "UEWSMVP|${runId}|${sentAt}|${pairIndex}|${seq}" in source
    assert "UEWSMVP\\\\|${runId}\\\\|" in compact


def test_message_writes_use_json_and_run_scoped_idempotency() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    send_message = source.split("function sendSyntheticMessage", maxsplit=1)[1].split(
        "export default function", maxsplit=1
    )[0]

    assert "JSON.stringify({ content })" in send_message
    assert re.search(
        r'["\']Content-Type["\']:\s*["\']application/json["\']', send_message
    )
    assert "Idempotency-Key" in send_message
    assert "ws-mvp-${runId}-${pairIndex}-${seq}" in send_message


def test_all_connections_must_remain_open_for_the_complete_profile_duration() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    compact = re.sub(r"\s+", "", source)

    assert 'new Counter("ws_mvp_connections_opened")' in source
    assert 'new Counter("ws_mvp_connections_closed")' in source
    assert re.search(r'new Rate\(\s*"ws_mvp_connection_duration_success"', source)
    assert re.search(r'new Trend\(\s*"ws_mvp_connection_duration_ms",\s*true\)', source)
    assert "ws_mvp_connections_opened: [`count==${PROFILE.connectionCount}`]" in source
    assert "ws_mvp_connections_closed: [`count==${PROFILE.connectionCount}`]" in source
    assert 'ws_mvp_connection_duration_success: ["rate==1"]' in source
    assert "constdurationMs=Date.now()-connectionOpenedAt" in compact
    assert "connectionDuration.add(durationMs)" in compact


def test_disposable_fixture_cleanup_and_outputs_do_not_expose_or_delete_credentials() -> (
    None
):
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    compact = re.sub(r"\s+", "", source)
    setup = source.split("export function setup()", maxsplit=1)[1].split(
        "function requestTicket", maxsplit=1
    )[0]

    assert "Do not point it at a shared/persistent stand" in source
    assert "no cleanup" in source
    assert "Message deletion is intentionally outside this load script" in source
    assert "owner must tear down only the isolated Compose project" in source
    assert "never point this harness at a persistent stand" in source
    assert "WS_MVP_DISPOSABLE_TARGET_CONFIRMATION" in setup
    assert '"I_UNDERSTAND_SYNTHETIC_DATA"' in setup
    assert "UEWSMVP|${runId}|${sentAt}|${pairIndex}|${seq}" in source
    assert "ws-mvp-${runId}-${pairIndex}-${seq}" in source
    assert re.search(r"systemTags:\s*\[[^\]]*\]", source)
    system_tags = re.search(r"systemTags:\s*(\[[^\]]*\])", source)
    assert system_tags is not None and '"url"' not in system_tags.group(1)
    failure_handler = source.split("function failSetup", maxsplit=1)[1].split(
        "function isLiteralIpAddress", maxsplit=1
    )[0]
    assert "accessToken" not in failure_handler
    assert "response.body" not in source
    assert "http.delete(" not in source
    assert 'method: "DELETE"' not in source
    assert not re.search(r"console\.(?:log|info|warn|error|debug)\s*\(", source)
    assert "JSON.stringify(pairs)" not in compact
    assert "JSON.stringify(participant)" not in compact


def test_profile_fails_closed_on_fixture_target_and_source_ip_requirements() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    compact = re.sub(r"\s+", "", source)

    assert "WS_MVP_PAIR_FIXTURE_PATH" in source
    assert "pairs.length !== PROFILE.pairCount" in source
    assert "userIds.size !== PROFILE.connectionCount" in source
    assert "WS_MVP_DISPOSABLE_TARGET_CONFIRMATION" in source
    assert "I_UNDERSTAND_SYNTHETIC_DATA" in source
    assert "WS_MVP_SOURCE_IPS" in source
    assert "PROFILE.minimumSourceIpCount" in source
    assert "at least 31 minutes" in source
    assert "no cleanup" in source
    assert "access_token" in source
    assert "UUID_PATTERN.test(pair.chat_id)" in source
    assert "sleep(PROFILE.connectionDurationMs/1000+60)" in compact
    assert "console.log" not in source
    assert "console.error" not in source

    hub_source = WS_HUB_PATH.read_text(encoding="utf-8")
    assert "NewWSUpgradeRateLimiter(10, 60)" in hub_source


def test_run_requires_a_compose_project_bound_to_its_synthetic_run_id() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    setup = source.split("export function setup()", maxsplit=1)[1].split(
        "function requestTicket", maxsplit=1
    )[0]

    assert "WS_MVP_COMPOSE_PROJECT" in setup
    assert "ue-mvp-${__ENV.WS_MVP_RUN_ID.toLowerCase()}" in setup
    assert "separate disposable Compose project" in source
    assert '-p "ue-mvp-${WS_MVP_RUN_ID,,}"' in source


def test_ci_validates_profile_without_running_load_or_starting_services() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    job_match = re.search(
        r"(?ms)^  ws-stress-test:\n(?P<job>.*?)(?=^  [a-z0-9][a-z0-9-]*:\s*$)",
        workflow,
    )
    assert job_match is not None
    job = job_match.group("job")

    assert "k6 inspect tests/performance/ws_hub_mvp_load_test.js" in job
    assert "k6 run tests/performance/ws_hub_mvp_load_test.js" not in job
    assert "docker compose up" not in job
