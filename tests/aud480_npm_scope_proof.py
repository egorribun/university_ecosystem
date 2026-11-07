"""Exercise the AUD-480 npm gate against a local synthetic registry."""

from __future__ import annotations

import gzip
import json
import os
import shlex
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/reusable-security-audit.yml"
pytest_plugins = ("pytester",)
DEPENDENCIES = {
    "fixture-prod": ("dependencies", {}),
    "fixture-dev": ("devDependencies", {"dev": True}),
    "fixture-optional": ("optionalDependencies", {"optional": True}),
    "fixture-peer": ("peerDependencies", {"peer": True}),
}


def _npm_invocation() -> list[str]:
    npm = shutil.which("npm")
    if npm is None:
        pytest.fail("npm is required to exercise its audit behavior", pytrace=False)
    if os.name != "nt":
        return [npm]
    node = shutil.which("node")
    if node is None:
        pytest.fail("Node is required to exercise npm audit", pytrace=False)
    npm_cli = Path(node).parent / "node_modules/npm/bin/npm-cli.js"
    if not npm_cli.is_file():
        pytest.fail("the Node installation's npm CLI is unavailable", pytrace=False)
    return [node, str(npm_cli)]


def _audit_arguments() -> list[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["npm-audit"]["steps"]
    gate = next(
        step
        for step in steps
        if step.get("name") == "Block moderate and low npm advisories"
    )
    command = shlex.split(gate["run"].strip().splitlines()[-1])
    assert command[:2] == ["npm", "audit"]
    safe_options = {
        *(
            f"--audit-level={level}"
            for level in ("info", "low", "moderate", "high", "critical")
        ),
        *(f"--include={group}" for group in ("prod", "dev", "optional", "peer")),
        *(f"--omit={group}" for group in ("dev", "optional", "peer")),
    }
    assert all(option in safe_options for option in command[2:])
    return command[1:]


@pytest.mark.parametrize(
    ("name", "severity", "omit"),
    [
        ("fixture-prod", "info", "dev"),
        ("fixture-dev", "low", "dev"),
        ("fixture-optional", "moderate", "optional"),
        ("fixture-peer", "high", "peer"),
        ("fixture-dev", "critical", "dev"),
    ],
)
def test_audit_blocks_every_severity_and_includes_omitted_groups(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    severity: str,
    omit: str,
) -> None:
    # The local registry supplies only synthetic metadata; no real packages or
    # network advisories are downloaded. Capture npm's actual audit payload.
    requests: list[dict[str, list[str]]] = []

    class Registry(BaseHTTPRequestHandler):
        def _reply(self, payload: object) -> None:
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            assert self.path == "/-/npm/v1/security/advisories/bulk"
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            requests.append(json.loads(raw))
            self._reply(
                {
                    name: [
                        {
                            "id": 123,
                            "name": name,
                            "url": "https://example.test/advisory/123",
                            "title": "Synthetic advisory",
                            "severity": severity,
                            "vulnerable_versions": "<2.0.0",
                        }
                    ]
                }
            )

        def do_GET(self) -> None:
            package = unquote(self.path.lstrip("/"))
            self._reply(
                {
                    "name": package,
                    "versions": {"1.0.0": {"name": package, "version": "1.0.0"}},
                    "dist-tags": {"latest": "1.0.0"},
                }
            )

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root: dict[str, object] = {"name": "scope-fixture", "version": "1.0.0"}
        packages: dict[str, object] = {"": root}
        for package, (group, flags) in DEPENDENCIES.items():
            root[group] = {package: "1.0.0"}
            packages[f"node_modules/{package}"] = {"version": "1.0.0", **flags}
        (pytester.path / "package.json").write_text(json.dumps(root), encoding="utf-8")
        (pytester.path / "package-lock.json").write_text(
            json.dumps(
                {**root, "lockfileVersion": 3, "requires": True, "packages": packages}
            ),
            encoding="utf-8",
        )
        for key in list(os.environ):
            if key.lower().startswith("npm_config_"):
                monkeypatch.delenv(key)
        env = dict(
            NODE_ENV="production",
            npm_config_omit=omit,
            npm_config_registry=f"http://127.0.0.1:{server.server_port}",
            npm_config_userconfig=str(pytester.path / "empty-user-npmrc"),
            npm_config_globalconfig=str(pytester.path / "empty-global-npmrc"),
            npm_config_cache=str(pytester.path / "cache"),
            npm_config_fetch_retries="0",
            npm_config_fetch_timeout="1000",
            npm_config_update_notifier="false",
            npm_config_proxy="http://127.0.0.1:1",
            npm_config_https_proxy="http://127.0.0.1:1",
            NO_PROXY="127.0.0.1,localhost",
        )
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        result = pytester.run(
            *_npm_invocation(), *_audit_arguments(), "--json", timeout=20
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.ret == 1, (result.stdout.str(), result.stderr.str())
    assert not result.stderr.str(), result.stderr.str()
    assert (
        json.loads(result.stdout.str())["vulnerabilities"][name]["severity"] == severity
    )
    assert requests == [{package: ["1.0.0"] for package in DEPENDENCIES}]
