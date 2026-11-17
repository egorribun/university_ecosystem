"""Owned kind-only live SPIRE lifecycle proof; never usable as a release bypass."""

from __future__ import annotations

import argparse
import json
import re
import select
import subprocess
import time
from contextlib import contextmanager
from typing import Any

HEX = re.compile(r"[0-9a-f]+")
LABEL = "university-ecosystem.io/ssr-lifecycle"
BINARY = "/ssr-mtls-fixture"
SOCKET = "unix:///spiffe-workload-api/agent.sock"


class ProofError(RuntimeError):
    """A required observation was absent or inconsistent."""


def receipt(text: str, expected: str) -> dict[str, Any]:
    """Accept only the fixture's bounded public-material receipt."""
    if len(text) > 8192:
        raise ProofError("oversized identity receipt")
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {
        "selfID", "leafSHA256", "leafNotAfterUnix", "issuerKeyID", "roots"
    }:
        raise ProofError("invalid identity receipt fields")
    if value["selfID"] != expected:
        raise ProofError("unexpected issued identity")
    if not isinstance(value["leafSHA256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["leafSHA256"]
    ):
        raise ProofError("invalid leaf fingerprint")
    if type(value["leafNotAfterUnix"]) is not int or value["leafNotAfterUnix"] <= time.time():
        raise ProofError("expired identity")
    roots = value["roots"]
    if not isinstance(roots, list) or not 1 <= len(roots) <= 16:
        raise ProofError("invalid root inventory")
    if any(not isinstance(item, str) or not HEX.fullmatch(item) for item in roots):
        raise ProofError("invalid root identifier")
    if len(set(roots)) != len(roots) or value["issuerKeyID"] not in roots:
        raise ProofError("identity issuer absent from local bundle")
    return value


def authority_id(value: Any) -> str:
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ProofError("invalid authority ID")
    return value


def wait_for(check: Any, seconds: int = 180) -> Any:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (ProofError, subprocess.SubprocessError, ValueError, KeyError):
            pass
        time.sleep(2)
    raise ProofError("bounded live observation did not converge")


class Lifecycle:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.ns = args.namespace
        self.front = f"{args.release}-university-ecosystem-frontend"
        self.backend = f"{args.release}-university-ecosystem-backend"
        self.self_id = f"spiffe://{args.trust_domain}/ns/{self.ns}/sa/{args.release}-frontend"
        self.peer_id = f"spiffe://{args.trust_domain}/ns/{self.ns}/sa/{args.release}-backend"
        self.wrong_id = f"spiffe://{args.trust_domain}/ns/{self.ns}/sa/ssr-wrong-peer"
        self.pods: list[str] = []

    def command(self, *args: str, data: str | None = None, timeout: int = 30) -> str:
        result = subprocess.run(
            ["kubectl", *args], input=data, text=True, capture_output=True,
            timeout=timeout, check=False,
        )
        if result.returncode:
            raise ProofError("Kubernetes operation failed")
        return result.stdout

    def kubectl(self, *args: str, **kwargs: Any) -> str:
        return self.command("-n", self.ns, *args, **kwargs)

    def ca(self, *args: str) -> dict[str, Any]:
        output = self.command(
            "-n", self.args.spire_namespace, "exec", "spire-server-0", "--",
            "/opt/spire/bin/spire-server", "localauthority", "x509", *args,
            "-output", "json",
        )
        return json.loads(output)

    def inspect(self, pod: str, identity: str) -> dict[str, Any]:
        return receipt(self.kubectl("exec", pod, "--", BINARY, "inspect"), identity)

    def peer(self, pod: str) -> dict[str, Any]:
        return receipt(self.kubectl("exec", pod, "--", BINARY, "peer"), self.peer_id)

    def fixture(self, name: str, account: str, identity: str, mode: str, peer: str) -> str:
        pod = f"ssr-lifecycle-{name}"
        labels = {
            "app.kubernetes.io/name": "university-ecosystem",
            "app.kubernetes.io/instance": self.args.release,
            "app.kubernetes.io/component": "frontend" if mode == "idle" else "backend",
            LABEL: pod,
        }
        env = {
            "SPIFFE_ENDPOINT_SOCKET": SOCKET,
            "FIXTURE_SELF_ID": identity,
            "FIXTURE_PEER_ID": peer,
            "FIXTURE_URL": f"https://{self.backend}:8000/health/ready",
        }
        manifest = {
            "apiVersion": "v1", "kind": "Pod",
            "metadata": {"name": pod, "namespace": self.ns, "labels": labels},
            "spec": {
                "serviceAccountName": account, "automountServiceAccountToken": False,
                "restartPolicy": "Never",
                "securityContext": {"runAsNonRoot": True, "runAsUser": 65532,
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{
                    "name": "fixture", "image": self.args.image,
                    "command": [BINARY, mode],
                    "ports": [{"name": "http", "containerPort": 8000, "protocol": "TCP"}],
                    "env": [{"name": key, "value": value} for key, value in env.items()],
                    "securityContext": {"allowPrivilegeEscalation": False,
                                        "readOnlyRootFilesystem": True,
                                        "capabilities": {"drop": ["ALL"]}},
                    "resources": {"requests": {"cpu": "20m", "memory": "32Mi"},
                                  "limits": {"cpu": "250m", "memory": "128Mi"}},
                    "volumeMounts": [{"name": "workload", "mountPath": "/spiffe-workload-api",
                                      "readOnly": True}],
                }],
                "volumes": [{"name": "workload", "csi": {"driver": "csi.spiffe.io", "readOnly": True}}],
            },
        }
        self.kubectl("create", "-f", "-", data=json.dumps(manifest))
        self.pods.append(pod)
        self.kubectl("wait", f"pod/{pod}", "--for=condition=Ready", "--timeout=120s", timeout=130)
        return pod

    def route(self, selector: dict[str, str]) -> None:
        self.kubectl("patch", "service", self.backend, "--type=json", "-p",
                     json.dumps([{"op": "replace", "path": "/spec/selector", "value": selector}]))

    def proxy_status(self) -> int:
        script = (
            "const r=await fetch('http://127.0.0.1:18000/health/ready',"
            "{redirect:'manual',signal:AbortSignal.timeout(8000)});"
            "console.log('STATUS='+r.status)"
        )
        output = self.kubectl("exec", f"deployment/{self.front}", "-c", "frontend",
                              "--", "node", "--input-type=module", "-e", script)
        if not re.fullmatch(r"STATUS=[1-5][0-9]{2}\n", output):
            raise ProofError("invalid proxy status receipt")
        return int(output[7:10])

    def identities(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for deployment in (self.front, self.backend):
            doc = json.loads(self.kubectl("get", "deployment", deployment, "-o", "json"))
            labels = doc["spec"]["selector"]["matchLabels"]
            selector = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
            pods = json.loads(self.kubectl("get", "pods", "-l", selector, "-o", "json"))["items"]
            # Fixture pods use baseline backend labels but are not Deployment-owned.
            pods = [pod for pod in pods if pod["metadata"].get("ownerReferences")]
            if not pods:
                raise ProofError("application deployment has no pods")
            result[deployment] = sorted(
                (pod["metadata"]["uid"],
                 tuple(sorted((c["name"], c["restartCount"])
                              for c in pod["status"]["containerStatuses"])))
                for pod in pods
            )
        return result

    @contextmanager
    def stream(self) -> Any:
        script = """
const signal=AbortSignal.timeout(25000);
try {
 const r=await fetch('http://127.0.0.1:18000/stream',{signal});
 if(r.status!==200) throw Error('not established');
 const reader=r.body.getReader(); let prefix='';
 while(!prefix.endsWith('\\n')) {
  const first=await reader.read();
  if(first.done) throw Error('bad stream');
  prefix+=new TextDecoder().decode(first.value);
  if(prefix.length>5) throw Error('bad stream');
 }
 if(prefix!=='OPEN\\n') throw Error('bad stream');
 console.log('OPEN');
 try { while(!(await reader.read()).done) {} throw Error('EOF'); }
 catch(error) { if(signal.aborted || error.message==='EOF') throw error; console.log('CANCELLED'); }
} catch { process.exitCode=1; }
"""
        process = subprocess.Popen(
            ["kubectl", "-n", self.ns, "exec", f"deployment/{self.front}", "-c", "frontend",
             "--", "node", "--input-type=module", "-e", script],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        try:
            if process.stdout is None or not select.select([process.stdout], [], [], 10)[0]:
                raise ProofError("stream did not open")
            if process.stdout.readline() != "OPEN\n":
                raise ProofError("stream not authenticated")
            opened = time.monotonic()
            yield process
            output, _ = process.communicate(timeout=12)
            if time.monotonic() - opened >= 20:
                raise ProofError("cancellation exceeded generation-change bound")
            if process.returncode != 0 or output != "CANCELLED\n":
                raise ProofError("stale stream not cancelled by transport")
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

    def source_failure(self, client: str) -> None:
        ns = self.args.spire_namespace
        document = json.loads(self.command("-n", ns, "get", "daemonset", "spire-agent", "-o", "json"))
        original = document["spec"]["template"]["spec"].get("nodeSelector")
        if original and LABEL in original:
            raise ProofError("refusing to replace an existing selector")
        disabled = dict(original or {})
        disabled[LABEL] = "no-node-matches"
        try:
            with self.stream():
                self.command("-n", ns, "patch", "daemonset", "spire-agent", "--type=merge",
                             "-p", json.dumps({"spec": {"template": {"spec": {"nodeSelector": disabled}}}}))
            wait_for(lambda: self.proxy_status() == 502, seconds=20)
            try:
                self.inspect(client, self.self_id)
            except (ProofError, subprocess.TimeoutExpired):
                pass
            else:
                raise ProofError("workload source unexpectedly remained available")
        finally:
            self.command("-n", ns, "patch", "daemonset", "spire-agent", "--type=merge",
                         "-p", json.dumps({"spec": {"template": {"spec": {"nodeSelector": {**(original or {}), LABEL: None}}}}}))
            self.command("-n", ns, "rollout", "status", "daemonset/spire-agent", "--timeout=180s", timeout=190)
        wait_for(lambda: self.proxy_status() == 200)

    def run(self) -> None:
        service = json.loads(self.kubectl("get", "service", self.backend, "-o", "json"))
        original = service["spec"]["selector"]
        baseline = self.identities()
        try:
            client = self.fixture("client", f"{self.args.release}-frontend", self.self_id, "idle", self.peer_id)
            backend_client = self.fixture("backend-client", f"{self.args.release}-backend", self.peer_id, "idle", self.self_id)
            before = self.inspect(client, self.self_id)
            original_peer = self.peer(client)
            frozen = self.fixture("frozen", f"{self.args.release}-backend", self.peer_id, "serve", self.self_id)
            self.route({LABEL: frozen})
            wait_for(lambda: self.proxy_status() == 200)
            self.source_failure(client)
            print("PASS ssr-live-source-failure-and-recovery", flush=True)

            wrong = self.fixture("wrong", "ssr-wrong-peer", self.wrong_id, "serve", self.self_id)
            control = self.fixture("control", f"{self.args.release}-frontend", self.self_id, "idle", self.wrong_id)
            self.route({LABEL: wrong})
            wait_for(lambda: self.kubectl("exec", control, "--", BINARY, "check").strip() == "CHECK=200")
            if self.proxy_status() != 502:
                raise ProofError("same-CA wrong backend identity was accepted")
            print("PASS ssr-live-wrong-peer-same-ca", flush=True)

            self.route({LABEL: frozen})
            wait_for(lambda: self.proxy_status() == 200)
            frozen_receipt = receipt(self.kubectl("logs", frozen).splitlines()[0], self.peer_id)
            old = authority_id(self.ca("show")["active"]["authority_id"])
            if frozen_receipt["issuerKeyID"] != old or frozen_receipt["leafNotAfterUnix"] <= time.time() + 300:
                raise ProofError("old issuer evidence is stale or too close to expiry")
            with self.stream():
                new = authority_id(self.ca("prepare")["prepared_authority"]["authority_id"])
                if new == old:
                    raise ProofError("prepare reused the active authority")
            wait_for(lambda: set(self.inspect(client, self.self_id)["roots"]) == {old, new})
            print("PASS ssr-live-ca-overlap-retires-stale-stream", flush=True)
            self.ca("activate", "-authorityID", new)
            if authority_id(self.ca("show")["active"]["authority_id"]) != new:
                raise ProofError("new signer did not activate")
            with self.stream():
                self.ca("taint", "-authorityID", old)
            wait_for(lambda: self.inspect(client, self.self_id)["issuerKeyID"] == new)
            after = self.inspect(client, self.self_id)
            if after["leafSHA256"] == before["leafSHA256"]:
                raise ProofError("frontend SVID was not renewed")
            wait_for(lambda: self.inspect(backend_client, self.peer_id)["issuerKeyID"] == new)
            if self.identities() != baseline:
                raise ProofError("application restarted during live renewal")
            print("PASS ssr-live-forced-svid-renewal-without-restart", flush=True)

            # Freeze a new-generation backend before removing the old authority.
            fresh = self.fixture("fresh", f"{self.args.release}-backend", self.peer_id, "serve", self.self_id)
            # The exact frozen old peer must still work with the renewed client.
            # Otherwise a client-trust failure could masquerade as root removal.
            wait_for(lambda: self.proxy_status() == 200)
            self.ca("revoke", "-authorityID", old)
            wait_for(lambda: set(self.inspect(client, self.self_id)["roots"]) == {new})
            wait_for(lambda: set(self.inspect(backend_client, self.peer_id)["roots"]) == {new})
            if frozen_receipt["leafNotAfterUnix"] <= time.time():
                raise ProofError("old credential expired before removal negative control")
            if self.proxy_status() != 502:
                raise ProofError("frozen old-authority backend was accepted after removal")
            self.route({LABEL: fresh})
            wait_for(lambda: self.proxy_status() == 200)
            print("PASS ssr-live-old-root-rejected-new-root-accepted", flush=True)
            self.route(original)
            wait_for(lambda: self.proxy_status() == 200)
            # Observe the actual application's authenticated TLS leaf, not just
            # another process using the same SPIRE registration.
            wait_for(lambda: self.peer(client)["issuerKeyID"] == new)
            production_peer = self.peer(client)
            if production_peer["leafSHA256"] == original_peer["leafSHA256"]:
                raise ProofError("production backend TLS identity was not renewed")
            if set(production_peer["roots"]) != {new}:
                raise ProofError("production backend check retained the old root")
        finally:
            self.route(original)
            for pod in reversed(self.pods):
                self.kubectl("delete", "pod", pod, "--wait=true", "--timeout=60s", timeout=70)
        wait_for(lambda: self.proxy_status() == 200)
        if self.identities() != baseline:
            raise ProofError("application restarted during CA lifecycle")
        print("PASS ssr-live-production-backend-recovered", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--spire-namespace", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--trust-domain", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        Lifecycle(args).run()
    except (ProofError, subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError):
        print("FAIL ssr-live-spiffe-lifecycle", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
