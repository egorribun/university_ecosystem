"""Exercise the alert-rule generator without running external tools."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from scripts.quality import check_prometheus_alert_rules as alert_contract

ROOT = Path(__file__).resolve().parents[2]


def test_prometheus_generator_preserves_actual_rule_groups() -> None:
    source = ROOT / "k8s/monitoring/prometheus-rules.yaml"
    manifest = yaml.safe_load(source.read_text(encoding="utf-8"))

    assert alert_contract.rules() == {"groups": manifest["spec"]["groups"]}


def _existing_prometheus_image() -> str:
    source = ROOT / "docker-compose.observability.yml"
    node = yaml.compose(
        source.read_text(encoding="utf-8"),
        Loader=yaml.SafeLoader,
    )
    for name in ("services", "prometheus", "image"):
        assert isinstance(node, yaml.MappingNode)
        assert node.tag == "tag:yaml.org,2002:map"
        matches = [
            value
            for key, value in node.value
            if isinstance(key, yaml.ScalarNode)
            and key.tag == "tag:yaml.org,2002:str"
            and key.value == name
        ]
        assert len(matches) == 1
        node = matches[0]

    assert isinstance(node, yaml.ScalarNode)
    assert node.tag == "tag:yaml.org,2002:str"
    return node.value


def test_prometheus_generator_uses_the_existing_compose_image() -> None:
    assert alert_contract.image() == _existing_prometheus_image()


@pytest.mark.parametrize(
    "reference",
    [
        "prom/prometheus:latest",
        "prom/prometheus:v3.15.0",
        "untrusted/prometheus:v3.15.0@sha256:" + "a" * 64,
        "prom/prometheus:v3.15.0@sha256:" + "a" * 63,
    ],
)
def test_prometheus_generator_image_cli_rejects_unpinned_or_wrong_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reference: str,
) -> None:
    (tmp_path / "docker-compose.observability.yml").write_text(
        yaml.safe_dump({"services": {"prometheus": {"image": reference}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(alert_contract, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["alert-contract", "image"])

    with pytest.raises(ValueError, match="immutable official Prometheus image"):
        alert_contract.main()

    assert capsys.readouterr().out == ""


def test_prometheus_generator_has_six_actual_metric_boundary_cases() -> None:
    generated = alert_contract.fixture()
    assert generated["rule_files"] == ["rules.json"]
    assert generated["evaluation_interval"] == "30s"
    tests = generated["tests"]
    assert isinstance(tests, list)
    assert len(tests) == 6
    by_name = {case["name"]: case for case in tests}
    assert len(by_name) == 6

    expected = {
        "OutboxStagnant": (
            {"outbox_pending_events_total": 101},
            {"outbox_pending_events_total": 100},
            "4m30s",
            "5m",
        ),
        "DatabasePoolSaturation": (
            {"db_pool_checkedout": 9, "db_pool_size": 10},
            {"db_pool_checkedout": 8, "db_pool_size": 10},
            "4m30s",
            "5m",
        ),
        "DatabasePoolExhausted": (
            {"db_pool_checkedout": 10, "db_pool_size": 10},
            {"db_pool_checkedout": 9, "db_pool_size": 10},
            "30s",
            "1m",
        ),
    }
    assert set(by_name) == {
        f"{alert}-{level}" for alert in expected for level in ("high", "low")
    }

    for alert, (high, low, pending_time, firing_time) in expected.items():
        for level, series in (("high", high), ("low", low)):
            case = by_name[f"{alert}-{level}"]
            assert case["interval"] == "30s"
            assert case["input_series"] == [
                {"series": name, "values": f"{value}+0x12"}
                for name, value in series.items()
            ]
            checks = case["promql_expr_test"]
            if level == "high":
                expected_checks = [
                    (pending_time, "pending", 1),
                    (pending_time, "firing", 0),
                    (firing_time, "pending", 0),
                    (firing_time, "firing", 1),
                ]
            else:
                expected_checks = [
                    ("6m", "pending", 0),
                    ("6m", "firing", 0),
                ]

            assert len(checks) == len(expected_checks)
            for check, (time, state, value) in zip(
                checks, expected_checks, strict=True
            ):
                assert check == {
                    "expr": (
                        f'count(ALERTS{{alertname="{alert}",'
                        f'alertstate="{state}"}}) or vector(0)'
                    ),
                    "eval_time": time,
                    "exp_samples": [{"labels": "{}", "value": value}],
                }


def test_prometheus_image_cli_ignores_unrelated_compose_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference = _existing_prometheus_image()
    (tmp_path / "docker-compose.observability.yml").write_text(
        "services:\n"
        "  unrelated:\n"
        "    ports: !override []\n"
        "  prometheus:\n"
        f"    image: {reference}\n"
        "    ports: !override []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(alert_contract, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["alert-contract", "image"])

    alert_contract.main()

    assert capsys.readouterr().out == f"{reference}\n"


@pytest.mark.parametrize(
    "document",
    [
        "services: {}\nservices: {}\n",
        "services:\n  prometheus: {}\n  prometheus: {}\n",
        "services:\n  prometheus:\n    image: $IMAGE\n    image: $IMAGE\n",
        "{}\n",
        "services: {}\n",
        "services:\n  prometheus: {}\n",
        "services: !override {}\n",
        "services:\n  prometheus: !override {}\n",
        "services:\n  prometheus:\n    image: !override $IMAGE\n",
        "services:\n  prometheus:\n    image: 123\n",
        "services:\n  prometheus:\n    image: {}\n",
        "services:\n  prometheus:\n    image: $IMAGE\n    123: ignored\n",
    ],
)
def test_prometheus_image_cli_rejects_ambiguous_or_nonstring_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    document: str,
) -> None:
    reference = _existing_prometheus_image()
    (tmp_path / "docker-compose.observability.yml").write_text(
        document.replace("$IMAGE", reference),
        encoding="utf-8",
    )
    monkeypatch.setattr(alert_contract, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["alert-contract", "image"])

    with pytest.raises(ValueError, match="immutable official Prometheus image"):
        alert_contract.main()

    assert capsys.readouterr().out == ""
