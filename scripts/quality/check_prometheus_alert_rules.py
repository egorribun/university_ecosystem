"""Generate behavioral fixtures for the shipped Kubernetes alert rules."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def image() -> str:
    node = yaml.compose(
        (ROOT / "docker-compose.observability.yml").read_text(encoding="utf-8"),
        Loader=yaml.SafeLoader,
    )
    message = "Expected the existing immutable official Prometheus image"
    for name in ("services", "prometheus", "image"):
        if not isinstance(node, yaml.MappingNode):
            raise ValueError(message)
        if node.tag != "tag:yaml.org,2002:map":
            raise ValueError(message)

        children = {}
        for key, value in node.value:
            if not isinstance(key, yaml.ScalarNode):
                raise ValueError(message)
            if key.tag != "tag:yaml.org,2002:str" or key.value in children:
                raise ValueError(message)
            children[key.value] = value

        if name not in children:
            raise ValueError(message)
        node = children[name]

    if not isinstance(node, yaml.ScalarNode):
        raise ValueError(message)
    if node.tag != "tag:yaml.org,2002:str" or not re.fullmatch(
        r"prom/prometheus:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", node.value
    ):
        raise ValueError(message)
    return node.value


def rules() -> dict[str, object]:
    manifest = yaml.safe_load(
        (ROOT / "k8s/monitoring/prometheus-rules.yaml").read_text(encoding="utf-8")
    )
    groups = manifest["spec"]["groups"]
    if not isinstance(groups, list) or not groups:
        raise ValueError("Expected nonempty Kubernetes alert groups")
    return {"groups": groups}


def state_check(alert: str, state: str, time: str, expected: int) -> dict[str, object]:
    return {
        "expr": (
            f'count(ALERTS{{alertname="{alert}",alertstate="{state}"}}) or vector(0)'
        ),
        "eval_time": time,
        "exp_samples": [{"labels": "{}", "value": expected}],
    }


def fixture() -> dict[str, object]:
    cases = [
        (
            "OutboxStagnant",
            {"outbox_pending_events_total": 101},
            {"outbox_pending_events_total": 100},
            "4m30s",
            "5m",
        ),
        (
            "DatabasePoolSaturation",
            {"db_pool_checkedout": 9, "db_pool_size": 10},
            {"db_pool_checkedout": 8, "db_pool_size": 10},
            "4m30s",
            "5m",
        ),
        (
            "DatabasePoolExhausted",
            {"db_pool_checkedout": 10, "db_pool_size": 10},
            {"db_pool_checkedout": 9, "db_pool_size": 10},
            "30s",
            "1m",
        ),
    ]
    tests = []
    for alert, high, low, pending_time, firing_time in cases:
        for label, series in (("high", high), ("low", low)):
            checks = []
            if label == "high":
                for time, pending, firing in (
                    (pending_time, 1, 0),
                    (firing_time, 0, 1),
                ):
                    checks.extend(
                        [
                            state_check(alert, "pending", time, pending),
                            state_check(alert, "firing", time, firing),
                        ]
                    )
            else:
                checks.extend(
                    [
                        state_check(alert, "pending", "6m", 0),
                        state_check(alert, "firing", "6m", 0),
                    ]
                )
            tests.append(
                {
                    "name": f"{alert}-{label}",
                    "interval": "30s",
                    "input_series": [
                        {"series": name, "values": f"{value}+0x12"}
                        for name, value in series.items()
                    ],
                    "promql_expr_test": checks,
                }
            )
    return {
        "rule_files": ["rules.json"],
        "evaluation_interval": "30s",
        "tests": tests,
    }


def main() -> None:
    args = sys.argv[1:]
    if args == ["image"]:
        print(image())
    elif args == ["rules"]:
        print(json.dumps(rules()))
    elif args == ["fixture"]:
        print(json.dumps(fixture()))
    else:
        raise SystemExit("Expected image, rules, or fixture")


if __name__ == "__main__":
    main()
