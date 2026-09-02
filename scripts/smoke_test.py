import os
import sys
import time

import requests


def check_health(url, name, timeout=30, interval=2):
    print(f"Checking {name} health at {url}...")
    start_time = time.time()

    while True:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"[OK] {name} is healthy!")
                return True
        except requests.exceptions.RequestException:
            pass

        elapsed = time.time() - start_time
        if elapsed >= timeout:
            print(f"[FAIL] {name} health check timed out after {timeout}s")
            return False

        print(f"Waiting for {name}... ({int(elapsed)}s elapsed)")
        time.sleep(interval)


def run_smoke_test():
    gateway_url = os.environ.get("GATEWAY_URL", "http://localhost:8080/health")
    ws_hub_url = os.environ.get("WS_HUB_URL", "http://localhost:8083/health")
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000/healthz")
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:8081/")

    results = [
        check_health(gateway_url, "Gateway"),
        check_health(ws_hub_url, "WS-Hub"),
        check_health(backend_url, "Python Backend"),
        check_health(frontend_url, "Frontend"),
    ]

    # LOW-W19: rust-optimizer is not present in the default compose stack; only
    # include its health check when RUST_OPTIMIZER_URL is explicitly set.
    rust_optimizer_url = os.environ.get("RUST_OPTIMIZER_URL")
    if rust_optimizer_url:
        results.append(check_health(rust_optimizer_url, "Rust Optimizer"))

    if all(results):
        print("[OK] All services are healthy! Smoke test passed.")
        sys.exit(0)
    else:
        print("[FAIL] Smoke test failed.")
        sys.exit(1)


if __name__ == "__main__":
    run_smoke_test()
