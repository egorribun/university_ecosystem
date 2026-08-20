"""Executable contracts for the local Docker launcher and build definitions."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _compose(relative_path: str) -> dict:
    # Compose's custom sequence tag is meaningful to Docker Compose but not to
    # PyYAML. Removing only the tag preserves the underlying data for contracts.
    return yaml.safe_load(_read(relative_path).replace("!override", ""))


def _powershell_function(script: str, name: str, next_name: str) -> str:
    start = script.index(f"function {name}")
    end = script.index(f"function {next_name}", start)
    return script[start:end]


def _env_values(relative_path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in _read(relative_path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_start_script_uses_cryptographic_randomness_for_secrets() -> None:
    script = _read("start-docker.ps1")
    secret_functions = _powershell_function(script, "New-Secret", "Write-Utf8NoBom")

    assert "RandomNumberGenerator" in secret_functions
    assert "Get-Random" not in secret_functions

    imgproxy_function = _powershell_function(
        script, "Ensure-ImgproxyEnvironment", "Ensure-MetricsEnvironment"
    )
    assert "(?:[0-9a-fA-F]{2}){$($spec.Bytes),}" in imgproxy_function
    assert "HexLength" not in imgproxy_function


def test_launcher_uses_the_prometheus_configured_metrics_identity() -> None:
    script = _read("start-docker.ps1")
    metrics_function = _powershell_function(
        script, "Ensure-MetricsEnvironment", "Ensure-ApplicationSecrets"
    )

    assert '$username = "metrics_scraper"' in metrics_function
    assert (
        'Get-EnvEntry -Path $EnvFile -Key "METRICS_BASIC_AUTH_USERNAME"'
        not in metrics_function
    )


def test_launcher_generates_documented_secret_lengths_and_syncs_rs256() -> None:
    script = _read("start-docker.ps1")
    fresh_setup = script[
        script.index("if ($needsEnvDocker -and $needsEnvCompose)") : script.index(
            "# Enable signed imgproxy URLs"
        )
    ]

    for variable in (
        "minioPassword",
        "redisPassword",
        "elasticPassword",
        "natsPassword",
        "grafanaPassword",
    ):
        assert re.search(rf"\${variable}\s*=\s*New-Secret -Length 32", fresh_setup)

    compose_env = fresh_setup.split('$composeEnv = @"', 1)[1].split('"@', 1)[0]
    assert "ALGORITHM=RS256" in compose_env
    assert "JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem" in compose_env
    assert "GRAFANA_ADMIN_USER=admin" in compose_env


def test_launcher_validates_and_reconciles_existing_rsa_material() -> None:
    script = _read("start-docker.ps1")
    private_key_function = _powershell_function(
        script, "New-JwtRs256Key", "New-JwtRs256PublicKey"
    )
    public_key_function = _powershell_function(
        script, "New-JwtRs256PublicKey", "ConvertTo-Base64Url"
    )

    assert "Test-JwtRs256PrivateKey" in private_key_function
    assert "invalid; regenerating" in private_key_function
    assert "RSA-2048 public key already exists" not in public_key_function
    assert "$existingPublicPem" in public_key_function
    assert "is current (idempotent skip)" in public_key_function


def test_launcher_pins_the_openssl_fallback_image() -> None:
    script = _read("start-docker.ps1")

    assert '$OpenSslFallbackImage = "alpine:3.20@sha256:' in script
    assert "docker run --rm alpine sh" not in script
    assert script.count("$OpenSslFallbackImage sh -c") == 3


def test_launcher_propagates_compose_errors_for_down_and_logs() -> None:
    script = _read("start-docker.ps1")
    down_block = script[script.index("if ($Down)") : script.index("# -- Handle -Logs")]
    logs_block = script[
        script.index("if ($Logs)") : script.index("# -- Generate secrets")
    ]

    for block in (down_block, logs_block):
        assert "$composeExitCode = $LASTEXITCODE" in block
        assert "exit $composeExitCode" in block


def test_temporal_token_claims_are_initialized_and_existing_token_is_validated() -> (
    None
):
    script = _read("start-docker.ps1")
    token_function = _powershell_function(
        script, "New-TemporalServiceToken", "Test-ServiceHttp"
    )

    payload_index = token_function.index("$payloadObj")
    for initialization in (
        "$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()",
        "$exp = $now + $ExpirationSeconds",
        '$jti = [Guid]::NewGuid().ToString("N")',
    ):
        assert initialization in token_function
        assert token_function.index(initialization) < payload_index

    assert "Test-TemporalServiceToken" in token_function
    assert "Valid existing Temporal service token" in token_function
    assert "Remove-Item" in token_function


def test_nightly_gate_mints_a_signed_temporal_service_jwt() -> None:
    workflow = _read(".github/workflows/nightly-full-gate.yml")

    assert '"alg":"RS256"' in workflow
    assert '"aud":"temporal"' in workflow
    assert "openssl dgst -sha256 -sign .secrets/jwt_rs256.pem" in workflow
    assert "nightly-temporal-token" not in workflow
    for name in ("IMGPROXY_KEY", "IMGPROXY_SALT"):
        assert re.search(rf"{name}: ['\"]?[0-9a-f]{{64}}['\"]?", workflow)


def test_docker_env_example_matches_full_stack_contract() -> None:
    values = _env_values(".env.docker.example")
    required = {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "SECRET_KEY",
        "ALGORITHM",
        "JWT_PRIVATE_KEY_PATH",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "ELASTIC_PASSWORD",
        "NATS_USER",
        "NATS_PASSWORD",
        "SPICEDB_PRESHARED_KEY",
        "WS_HUB_INTERNAL_SECRET",
        "GRAFANA_ADMIN_USER",
        "GRAFANA_ADMIN_PASSWORD",
        "IMGPROXY_KEY",
        "IMGPROXY_SALT",
        "IMGPROXY_BASE_URL",
        "ENABLE_METRICS_ENDPOINT",
        "METRICS_BASIC_AUTH_USERNAME",
        "METRICS_BASIC_AUTH_PASSWORD",
        "REDIS_PASSWORD",
        "ENVIRONMENT",
        "VAPID_SUBJECT",
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "SPOTIFY_REDIRECT_URI",
        "SPOTIFY_SCOPES",
    }

    assert required <= values.keys(), (
        f"missing keys: {sorted(required - values.keys())}"
    )
    assert values["ALGORITHM"] == "RS256"
    assert values["JWT_PRIVATE_KEY_PATH"] == ".secrets/jwt_rs256.pem"
    assert values["IMGPROXY_BASE_URL"] == "http://localhost/imgproxy"
    assert values["ENABLE_METRICS_ENDPOINT"].lower() == "true"
    assert values["METRICS_BASIC_AUTH_USERNAME"] == "metrics_scraper"


def test_imgproxy_signing_is_wired_end_to_end() -> None:
    launcher = _read("start-docker.ps1")

    assert "$imgproxyKey" in launcher
    assert "$imgproxySalt" in launcher
    assert "Ensure-ImgproxyEnvironment" in launcher
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        compose = _compose(relative_path)
        image_proxy = compose["services"]["imgproxy"]["environment"]
        assert "is required" in image_proxy["IMGPROXY_KEY"]
        assert "is required" in image_proxy["IMGPROXY_SALT"]

    for relative_path in ("services/caddy/Caddyfile", "infrastructure/Caddyfile"):
        caddyfile = _read(relative_path)
        assert "handle_path /imgproxy/*" in caddyfile
        assert "reverse_proxy imgproxy:8080" in caddyfile


def test_all_caddy_configs_expose_the_same_auth_and_websocket_routes() -> None:
    for relative_path in ("services/caddy/Caddyfile", "infrastructure/Caddyfile"):
        caddyfile = _read(relative_path)

        assert "handle /.well-known/*" in caddyfile
        assert "handle /api/*" in caddyfile
        assert "handle /ws/ticket" in caddyfile
        assert "handle /ws/chat*" in caddyfile
        assert "rewrite * /ws" in caddyfile
        assert "reverse_proxy gateway:8080" in caddyfile
        assert "reverse_proxy ws-hub:8081" in caddyfile
        assert (
            caddyfile.index("handle /ws/ticket")
            < caddyfile.index("handle /ws/chat*")
            < caddyfile.index("handle /ws/*")
        )

    production = _read("services/caddy/Caddyfile")
    api_block = production[
        production.index("handle /api/*") : production.index("handle /graphql*")
    ]
    assert re.search(r"health_uri\s+/health(?:\s|$)", api_block)
    assert "health_uri /healthz" not in api_block


def test_minio_bucket_initialization_is_compose_managed_and_fail_fast() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(relative_path)["services"]
        init = services["minio-init"]

        assert init["depends_on"]["minio"]["condition"] == "service_healthy"
        assert init["environment"]["MC_CONFIG_DIR"] == "/mc-config"
        assert init["read_only"] is True
        assert "/mc-config:size=1m,mode=0700" in init["tmpfs"]
        assert "mc mb local/uploads --ignore-existing" in init["command"][0]
        assert "$${MINIO_ROOT_PASSWORD}" in init["command"][0]
        assert services["backend"]["depends_on"]["minio-init"]["condition"] == (
            "service_completed_successfully"
        )

    for relative_path in ("docker-compose.go.yml", "docker-compose.full.yml"):
        file_processor = _compose(relative_path)["services"]["file-processor"]
        assert file_processor["depends_on"]["minio-init"]["condition"] == (
            "service_completed_successfully"
        )

    launcher = _read("start-docker.ps1")
    assert "Ensuring MinIO 'uploads' bucket exists" not in launcher
    assert "docker run --rm --network $network" not in launcher


def test_compose_wrappers_always_use_the_full_stack_env_file() -> None:
    for relative_path in ("scripts/dc.ps1", "scripts/dc.sh"):
        wrapper = _read(relative_path)
        assert ".env.docker" in wrapper
        assert "--env-file" in wrapper
        assert "docker-compose.full.yml" in wrapper


def test_start_script_removes_obsolete_containers_and_waits_for_the_full_stack() -> (
    None
):
    script = _read("start-docker.ps1")
    services_start = script.index("$services = [ordered]@{")
    services_block = script[services_start : script.index("do {", services_start)]

    assert "up -d --remove-orphans" in script
    assert "--force-recreate" not in script
    assert "ps --all" in script
    assert (
        "logs --tail=50 migrations postgres-databases-init minio-init "
        "spicedb-migrate" in script
    )

    critical_services = {
        "postgres",
        "redis",
        "redis-exporter",
        "backend",
        "elasticsearch",
        "gateway",
        "minio",
        "temporal",
        "grafana",
        "notifications-worker",
        "prometheus",
        "frontend",
        "imgproxy",
        "nats",
        "outbox-worker",
        "spicedb",
        "ws-hub",
        "caddy",
        "file-processor",
        "loki-healthprobe",
        "tempo-healthprobe",
        "alloy",
        "pyroscope",
    }
    for service in critical_services:
        assert f'service = "{service}"' in services_block, service
    for name, url in {
        "minio": "http://localhost:9001/",
        "grafana": "http://localhost:3000/api/health",
        "prometheus": "http://localhost:9090/-/healthy",
        "frontend": "http://localhost:8081/login",
        "site": "http://localhost/login",
    }.items():
        entry = re.search(rf"{name}\s+= @\{{([^\n]+)", services_block)
        assert entry is not None, name
        assert 'type = "http"' in entry.group(1), name
        assert url in entry.group(1), name

    assert "timeout = 20" in re.search(
        r"frontend\s+= @\{([^\n]+)", services_block
    ).group(1)
    assert "Test-ServiceHttp -Url" in script
    assert "-Timeout $requestTimeout" in script


def test_published_ports_have_a_non_internal_network() -> None:
    """Docker cannot publish host ports from an internal-only bridge network."""
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        compose = _compose(relative_path)
        networks = compose["networks"]

        for service_name, service in compose["services"].items():
            if not service.get("ports"):
                continue
            service_networks = service.get("networks", [])
            assert any(
                not (networks.get(network_name) or {}).get("internal", False)
                for network_name in service_networks
            ), (relative_path, service_name)


def test_base_worker_metrics_are_reachable_only_through_loopback_publish() -> None:
    worker = _compose("docker-compose.yml")["services"]["notifications-worker"]

    # Docker's port forwarding cannot reach a process bound only to the
    # container loopback interface. Bind inside the container on all
    # interfaces, while keeping the published host socket on loopback.
    assert worker["environment"]["NOTIFICATIONS_WORKER_METRICS_HOST"] == "0.0.0.0"  # noqa: S104 - container bind; host port remains loopback-only
    assert "127.0.0.1:9102:9101" in worker["ports"]


def test_backend_compose_healthchecks_use_lean_readiness_endpoint() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        healthcheck = _compose(relative_path)["services"]["backend"]["healthcheck"]
        command = " ".join(str(part) for part in healthcheck["test"])

        assert "/health/ready" in command, relative_path
        assert "/healthz" not in command, relative_path


def test_tempo_uses_one_canonical_configuration() -> None:
    canonical_source = "./infrastructure/observability/tempo.yaml:"

    for relative_path in (
        "docker-compose.yml",
        "docker-compose.full.yml",
        "docker-compose.observability.yml",
    ):
        volumes = _compose(relative_path)["services"]["tempo"]["volumes"]
        assert any(str(volume).startswith(canonical_source) for volume in volumes), (
            relative_path
        )

    assert not (ROOT / "config/tempo.yaml").exists()


def test_temporal_waits_for_its_healthy_jwks_source() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        temporal = _compose(relative_path)["services"]["temporal"]
        assert temporal["depends_on"]["backend"]["condition"] == "service_healthy"


def test_rs256_backend_mounts_the_launcher_managed_keypair() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        backend = _compose(relative_path)["services"]["backend"]
        assert "./.secrets:/app/.secrets:ro" in backend["volumes"]


def test_file_processor_exports_traces_to_tempo() -> None:
    config = _read("services/file-processor/internal/config/config.go")
    main = _read("services/file-processor/cmd/file-processor/main.go")

    assert 'viper.SetDefault("otlp_endpoint", "tempo:4317")' in config
    assert 'endpoint = "tempo:4317"' in main
    assert "jaeger:4317" not in config
    assert "jaeger:4317" not in main

    for relative_path in ("docker-compose.full.yml", "docker-compose.go.yml"):
        environment = _compose(relative_path)["services"]["file-processor"][
            "environment"
        ]
        assert environment["FP_OTLP_ENDPOINT"] == "tempo:4317"
        assert str(environment["FP_OTLP_INSECURE"]).lower() == "true"


def test_gateway_exports_traces_to_tempo() -> None:
    config = _read("services/gateway/internal/config/config.go")
    gateway = _compose("docker-compose.full.yml")["services"]["gateway"]

    assert 'getEnv("OTEL_EXPORTER_OTLP_ENDPOINT", "tempo:4317")' in config
    assert "jaeger:4317" not in config
    assert gateway["environment"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "tempo:4317"


def test_config_rollouts_restart_telemetry_clients_after_tempo_is_ready() -> None:
    services = _compose("docker-compose.full.yml")["services"]

    for service_name in ("gateway", "file-processor"):
        service = services[service_name]
        assert (
            "DOCKER_CONFIG_REVISION"
            in service["labels"]["com.university-ecosystem.config-revision"]
        )
        assert service["depends_on"]["tempo-healthprobe"]["condition"] == (
            "service_healthy"
        )

    assert services["gateway"]["depends_on"]["backend"]["condition"] == (
        "service_healthy"
    )


def test_prometheus_scrapes_the_authenticated_backend_and_real_exporters() -> None:
    launcher = _read("start-docker.ps1")
    prometheus_config = _read("infrastructure/observability/prometheus.yml")

    assert "Ensure-MetricsEnvironment" in launcher
    assert "username: metrics_scraper" in prometheus_config
    assert "password_file: /tmp/backend_metrics_password" in (prometheus_config)
    assert "redis-exporter:9121" in prometheus_config
    assert "redis:6379" not in prometheus_config
    assert "nats:8222" not in prometheus_config

    full = _compose("docker-compose.full.yml")["services"]
    assert full["backend"]["environment"]["ENABLE_METRICS_ENDPOINT"] == "true"
    assert full["backend"]["environment"]["METRICS_BASIC_AUTH_USERNAME"] == (
        "metrics_scraper"
    )
    observability_backend = _compose("docker-compose.observability.yml")["services"][
        "backend"
    ]
    assert (
        observability_backend["environment"]["METRICS_BASIC_AUTH_USERNAME"]
        == "metrics_scraper"
    )
    assert "redis-exporter" in full
    assert full["minio"]["environment"]["MINIO_PROMETHEUS_AUTH_TYPE"] == ("public")
    prometheus_volumes = full["prometheus"]["volumes"]
    assert any(
        "prometheus.yml:/etc/prometheus/prometheus.yml:ro" in item
        for item in prometheus_volumes
    )
    assert "METRICS_BASIC_AUTH_PASSWORD" in full["prometheus"]["environment"]
    assert "/tmp/backend_metrics_password" in full["prometheus"]["command"][0]  # noqa: S108 - container contract

    alert_rules = _read("infrastructure/observability/alerts/gateway.yaml")
    assert "(mul " not in alert_rules
    assert "humanizePercentage" in alert_rules


def test_local_grafana_is_persistent_and_offline_safe() -> None:
    required_environment = {
        "GF_ANALYTICS_REPORTING_ENABLED": "false",
        "GF_ANALYTICS_CHECK_FOR_UPDATES": "false",
        "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES": "false",
        "GF_PLUGINS_PREINSTALL_DISABLED": "true",
        "GF_PLUGINS_PUBLIC_KEY_RETRIEVAL_DISABLED": "true",
    }
    for relative_path in (
        "docker-compose.full.yml",
        "docker-compose.observability.yml",
    ):
        grafana = _compose(relative_path)["services"]["grafana"]
        for key, expected in required_environment.items():
            assert str(grafana["environment"][key]).lower() == expected
        assert str(grafana["environment"]["GF_DATABASE_WAL"]).lower() == "true"
        assert any("/var/lib/grafana" in item for item in grafana["volumes"])
        assert not any(
            item.endswith("/etc/grafana/provisioning:ro") for item in grafana["volumes"]
        )


def test_full_stack_observability_is_wired_end_to_end() -> None:
    services = _compose("docker-compose.full.yml")["services"]

    assert "alloy" in services
    assert "pyroscope" in services
    assert "loki-healthprobe" in services["alloy"]["depends_on"]
    assert any("/var/tempo" in item for item in services["tempo"]["volumes"])
    assert any("/loki" in item for item in services["loki"]["volumes"])


def test_temporal_namespace_init_is_quietly_idempotent() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        command = _compose(relative_path)["services"]["temporal-namespace-init"][
            "command"
        ][0]

        cluster_health = command.index("temporal operator cluster health")
        describe = command.index("temporal operator namespace describe")
        create = command.index("temporal operator namespace create")
        assert cluster_health < describe < create
        assert "stabilization" in command


def test_temporal_frontend_binds_every_attached_compose_network() -> None:
    """The namespace/client network must reach a multi-network Temporal server."""
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(relative_path)["services"]
        temporal = services["temporal"]
        namespace_init = services["temporal-namespace-init"]

        assert temporal["environment"]["BIND_ON_IP"] == "0.0.0.0"  # noqa: S104
        assert set(temporal["networks"]) & set(namespace_init["networks"])

    temporal_config = yaml.safe_load(_read("services/temporal/config.yaml"))
    for service in ("frontend", "matching", "history", "worker"):
        rpc = temporal_config["services"][service]["rpc"]
        assert rpc["bindOnLocalHost"] is False
        assert rpc["bindOnIP"] == "0.0.0.0"  # noqa: S104


def test_postgres_database_bootstrap_is_cleanly_idempotent() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(relative_path)["services"]
        database_init = services["postgres-databases-init"]
        command = database_init["command"][0]

        assert "SELECT 1 FROM pg_database" in command
        for database in ("spicedb", "temporal", "temporal_visibility"):
            assert database in command
        assert database_init["depends_on"]["postgres"]["condition"] == (
            "service_healthy"
        )
        assert (
            services["spicedb"]["depends_on"]["postgres-databases-init"]["condition"]
            == "service_completed_successfully"
        )
        assert (
            services["temporal-admin-tools"]["depends_on"]["postgres-databases-init"][
                "condition"
            ]
            == "service_completed_successfully"
        )
        assert "create-database" not in services["temporal-admin-tools"]["command"][0]

    launcher = _read("start-docker.ps1")
    assert 'psql -U postgres -c "CREATE DATABASE spicedb"' not in launcher


def test_local_temporal_and_spicedb_opt_out_of_external_auth_telemetry_noise() -> None:
    assert "--allow-no-auth" in _read("services/temporal/entrypoint.sh")
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        command = _compose(relative_path)["services"]["spicedb"]["command"]
        assert "--telemetry-endpoint=" in command
        assert "--skip-release-check=true" in command


def test_spicedb_does_not_log_database_credentials_and_has_watch_support() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(relative_path)["services"]
        postgres = services["postgres"]
        migration = services["spicedb-migrate"]
        spicedb = services["spicedb"]

        assert "${POSTGRES_PASSWORD}" not in spicedb["command"]
        assert spicedb["environment"]["PGPASSWORD"].startswith("${POSTGRES_PASSWORD:?")
        assert "track_commit_timestamp=on" in postgres["command"]

        assert migration["image"] == spicedb["image"]
        assert migration["command"][:3] == ["datastore", "migrate", "head"]
        assert "--skip-release-check=true" in migration["command"]
        assert migration["environment"]["PGPASSWORD"].startswith(
            "${POSTGRES_PASSWORD:?"
        )
        assert migration["depends_on"]["postgres-databases-init"]["condition"] == (
            "service_completed_successfully"
        )
        assert spicedb["depends_on"]["spicedb-migrate"]["condition"] == (
            "service_completed_successfully"
        )

    launcher = _read("start-docker.ps1")
    assert "Running SpiceDB migrations" not in launcher
    assert "SpiceDB migration failed or already up-to-date" not in launcher


def test_launcher_manages_independent_application_secrets() -> None:
    launcher = _read("start-docker.ps1")
    example = _env_values(".env.docker.example")
    managed = {
        "CSRF_HMAC_SECRET",
        "INTERNAL_HMAC_SECRET",
        "IDEMPOTENCY_HMAC_SECRET",
        "SPOTIFY_TOKEN_SECRET",
        "SPOTIFY_OAUTH_STATE_SECRET",
    }

    assert "Ensure-ApplicationSecrets" in launcher
    assert "New-FernetKey" in launcher
    assert managed <= example.keys()
    for key in managed:
        assert key in launcher

    gateway = _compose("docker-compose.full.yml")["services"]["gateway"]
    assert gateway["environment"]["INTERNAL_HMAC_SECRET"] == (
        "${INTERNAL_HMAC_SECRET:?INTERNAL_HMAC_SECRET is required - run start-docker.ps1}"
    )


def test_launcher_waits_for_pyroscope_readiness_not_just_process_state() -> None:
    script = _read("start-docker.ps1")
    services_start = script.index("$services = [ordered]@{")
    services_block = script[services_start : script.index("do {", services_start)]
    entry = re.search(r"pyroscope\s+= @\{([^\n]+)", services_block)

    assert entry is not None
    assert 'type = "http"' in entry.group(1)
    assert "http://localhost:4040/ready" in entry.group(1)


def test_launcher_recreates_services_when_bind_mounted_configs_change() -> None:
    script = _read("start-docker.ps1")
    services = _compose("docker-compose.full.yml")["services"]

    assert "Ensure-DockerConfigRevision" in script
    for relative_path in (
        "config/nats.conf.template",
        "services/temporal/config.yaml",
        "infrastructure/observability/prometheus.yml",
        "infrastructure/observability/alloy/config.alloy",
        "infrastructure/Caddyfile",
    ):
        assert relative_path in script

    for service_name in (
        "nats",
        "temporal",
        "tempo",
        "loki",
        "alloy",
        "prometheus",
        "grafana",
        "caddy",
    ):
        assert (
            "DOCKER_CONFIG_REVISION"
            in services[service_name]["labels"][
                "com.university-ecosystem.config-revision"
            ]
        ), service_name


def test_launcher_requires_all_prometheus_targets_to_be_up() -> None:
    script = _read("start-docker.ps1")

    assert "Wait-PrometheusTargets" in script
    assert "Prometheus scrape targets are healthy" in script
    assert script.index("Wait-PrometheusTargets") < script.rindex(
        "Prometheus scrape targets are healthy"
    )


def test_compose_uses_one_supported_outbox_processor() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(relative_path)["services"]

        assert "debezium" not in services
        assert "cdc-outbox-worker" not in services
        assert services["outbox-worker"]["command"] == "python -m app.workers.outbox"
        assert "ENABLE_CDC_OUTBOX" not in services["outbox-worker"].get(
            "environment", {}
        )
        assert (
            str(services["backend"]["environment"]["EMBEDDED_OUTBOX_WORKER_ENABLED"])
            .strip()
            .lower()
            == "false"
        )


def test_nats_consumers_wait_for_a_healthy_broker() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(relative_path)["services"]

        assert "nats" in services
        for consumer in ("backend", "notifications-worker", "outbox-worker"):
            dependency = services[consumer]["depends_on"]["nats"]
            assert dependency["condition"] == "service_healthy"


def test_base_python_services_keep_nats_token_out_of_the_url() -> None:
    services = _compose("docker-compose.yml")["services"]
    expected_token = "${NATS_PASSWORD:?NATS_PASSWORD is required - set in .env file}"

    for service_name in ("backend", "notifications-worker", "outbox-worker"):
        environment = services[service_name]["environment"]
        assert environment["NATS_URL"] == "nats://nats:4222"
        assert environment["NATS_AUTH_TOKEN"] == expected_token

    assert services["nats"]["environment"]["NATS_AUTH_TOKEN"] == expected_token


def test_compose_has_no_hardcoded_or_optional_secret_fallbacks() -> None:
    secret_names = (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "NATS_PASSWORD",
        "MINIO_ROOT_PASSWORD",
        "ELASTIC_PASSWORD",
        "SECRET_KEY",
        "SPICEDB_PRESHARED_KEY",
        "WS_HUB_INTERNAL_SECRET",
        "GRAFANA_ADMIN_PASSWORD",
    )

    for relative_path in (
        "docker-compose.yml",
        "docker-compose.full.yml",
        "docker-compose.infra.yml",
        "docker-compose.observability.yml",
    ):
        compose_text = _read(relative_path)
        assert "DevRedisPass2024x" not in compose_text
        for name in secret_names:
            assert not re.search(rf"(?<!\$)\$\{{{name}(?:\}}|:-)", compose_text), (
                relative_path,
                name,
            )


def test_go_overlay_uses_the_base_nats_credential_contract() -> None:
    services = _compose("docker-compose.go.yml")["services"]

    for service_name, env_name in (
        ("ws-hub", "NATS_URL"),
        ("file-processor", "FP_NATS_URL"),
    ):
        nats_url = services[service_name]["environment"][env_name]
        assert "${NATS_PASSWORD:?" in nats_url
        assert "NATS_AUTH_TOKEN" not in nats_url

    ci_ws_hub_url = _compose("docker-compose.ci-loadtest.yml")["services"]["ws-hub"][
        "environment"
    ]["NATS_URL"]
    assert "${NATS_PASSWORD:?" in ci_ws_hub_url
    assert "NATS_AUTH_TOKEN" not in ci_ws_hub_url

    nightly = _read(".github/workflows/nightly-full-gate.yml")
    load_job = nightly.split("  load-and-chaos:", maxsplit=1)[1]
    assert "NATS_PASSWORD: nightly-nats-token" in load_job


def test_postgres_does_not_enable_retired_cdc_replication_settings() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        command = " ".join(
            str(part)
            for part in _compose(relative_path)["services"]["postgres"]["command"]
        )

        assert "track_commit_timestamp=on" in command
        assert "wal_level=logical" not in command
        assert "max_replication_slots" not in command
        assert "max_wal_senders" not in command


def test_file_processor_uses_prefixed_env_and_file_based_rs256_verification() -> None:
    for relative_path in ("docker-compose.full.yml", "docker-compose.go.yml"):
        service = _compose(relative_path)["services"]["file-processor"]
        environment = service["environment"]

        assert environment["FP_RSA_PUBLIC_KEY_FILE"] == (
            "/app/.secrets/jwt_rs256.pub.pem"
        )
        assert all(
            not key.startswith(("NATS_", "MINIO_", "JWT_")) for key in environment
        )
        assert "./.secrets:/app/.secrets:ro" in service["volumes"]


def test_outbox_healthcheck_requires_a_recent_event_loop_heartbeat() -> None:
    for relative_path in (
        "docker-compose.yml",
        "docker-compose.full.yml",
        "docker-compose.prod.yml",
    ):
        service = _compose(relative_path)["services"]["outbox-worker"]
        healthcheck = " ".join(str(part) for part in service["healthcheck"]["test"])

        assert "/tmp/worker.pid" in healthcheck  # noqa: S108 - container contract
        assert "/tmp/worker.heartbeat" in healthcheck  # noqa: S108 - container contract
        assert "getmtime" in healthcheck
        assert "sys.exit(0)" not in healthcheck


def test_production_pgbouncer_uses_a_supported_image_and_file_secret() -> None:
    compose = _compose("docker-compose.prod.yml")
    services = compose["services"]
    pgbouncer = services["pgbouncer"]
    postgres = services["postgres"]

    assert (
        pgbouncer["image"]
        == (
            "edoburu/pgbouncer:v1.25.2-p0@sha256:"
            "7d7a27d9e90985cab5cf42256f5c13a3120baa4b055b69df37beb272b89b2340"  # pragma: allowlist secret
        )
    )
    assert "postgres_password" in compose["secrets"]
    assert compose["secrets"]["postgres_password"]["file"].startswith(
        "${POSTGRES_PASSWORD_SOURCE_FILE:"
    )
    assert "postgres_password" in pgbouncer["secrets"]
    assert "postgres_password" in postgres["secrets"]
    assert postgres["environment"]["POSTGRES_PASSWORD_FILE"] == (
        "/run/secrets/postgres_password"
    )
    assert pgbouncer["environment"]["POOL_MODE"] == "transaction"
    assert pgbouncer["environment"]["SERVER_TLS_SSLMODE"] == "prefer"
    assert "5432" in " ".join(pgbouncer["healthcheck"]["test"])
    assert services["migrations"]["depends_on"]["pgbouncer"]["condition"] == (
        "service_healthy"
    )


def test_helm_outbox_scaler_targets_a_real_database_backed_worker() -> None:
    values = _compose("charts/university-ecosystem/values.yaml")
    deployment = _read(
        "charts/university-ecosystem/templates/outbox-worker-deployment.yaml"
    )
    backend = _read("charts/university-ecosystem/templates/backend-deployment.yaml")
    keda = _read("charts/university-ecosystem/templates/keda-scaledobjects.yaml")
    rbac = _read("charts/university-ecosystem/templates/rbac.yaml")
    network_policy = _read("charts/university-ecosystem/templates/network-policy.yaml")

    assert values["global"]["imageRegistry"] == ""
    assert "cdcWorker" not in values
    assert "wal_level" not in values["postgres"]
    assert "wal_level" not in values["postgresql"]
    assert values["postgres"]["config"]["track_commit_timestamp"] is True
    assert values["postgresql"]["config"]["track_commit_timestamp"] is True
    assert values["outboxWorker"]["enabled"] is True
    assert "python -m app.workers.outbox" in deployment
    assert "EMBEDDED_OUTBOX_WORKER_ENABLED" in backend
    assert backend.count("path: /health/ready") == 2
    assert "path: /health/live" in backend
    assert "path: /healthz" not in backend
    assert "type: postgresql" in keda
    assert "connectionFromEnv: KEDA_POSTGRESQL_CONNECTION" in keda
    assert "stored_events" in keda
    assert "OUTBOX_EVENTS" not in keda
    assert (
        'list "backend" "gateway" "frontend" "file-processor" "outbox-worker" "backup"'
        in rbac
    )
    assert "app.kubernetes.io/component: outbox-worker" in network_policy


def test_helm_references_only_real_workloads_and_services_select_their_pods() -> None:
    values = _compose("charts/university-ecosystem/values.yaml")
    file_processor_deployment = _read(
        "charts/university-ecosystem/templates/file-processor-deployment.yaml"
    )
    file_processor_service = _read(
        "charts/university-ecosystem/templates/file-processor-service.yaml"
    )
    gateway_service = _read(
        "charts/university-ecosystem/templates/gateway-service.yaml"
    )
    gateway_deployment = _read(
        "charts/university-ecosystem/templates/gateway-deployment.yaml"
    )
    secrets = _read("charts/university-ecosystem/templates/secrets.yaml")
    keda = _read("charts/university-ecosystem/templates/keda-scaledobjects.yaml")
    rbac = _read("charts/university-ecosystem/templates/rbac.yaml")
    network_policy = _read("charts/university-ecosystem/templates/network-policy.yaml")

    assert values["fileProcessor"]["enabled"] is True
    assert "rustOptimizer" not in values
    assert "rust-optimizer" not in keda
    assert ".Values.global.imagePullSecrets" in file_processor_deployment
    assert "FP_RSA_PUBLIC_KEY_FILE" in file_processor_deployment
    assert "jwt-rsa-public-key" in secrets
    assert "app.kubernetes.io/component: file-processor" in file_processor_service
    assert "university-ecosystem.selectorLabels" in file_processor_service
    assert "app: gateway" not in gateway_service
    assert "university-ecosystem.selectorLabels" in gateway_service
    assert 'prometheus.io/port: "9102"' in gateway_deployment
    assert 'prometheus.io/path: "/metrics"' in gateway_deployment
    assert "containerPort: 9102" in gateway_deployment
    assert (
        'list "backend" "gateway" "frontend" "file-processor" "outbox-worker" "backup"'
        in rbac
    )
    assert "app.kubernetes.io/component: file-processor" in network_policy


def test_helm_images_do_not_gain_a_leading_slash_when_registry_is_empty() -> None:
    deployments = (
        "backend-deployment.yaml",
        "frontend-deployment.yaml",
        "gateway-deployment.yaml",
        "file-processor-deployment.yaml",
        "outbox-worker-deployment.yaml",
    )
    for name in deployments:
        deployment = _read(f"charts/university-ecosystem/templates/{name}")
        assert 'trimPrefix "/"' in deployment, name
        assert ".Values.global.imagePullSecrets" in deployment, name


def test_helm_frontend_matches_the_node_ssr_runtime_contract() -> None:
    values = _compose("charts/university-ecosystem/values.yaml")
    deployment = _read("charts/university-ecosystem/templates/frontend-deployment.yaml")
    network_policy = _read("charts/university-ecosystem/templates/network-policy.yaml")

    assert values["frontend"]["service"]["port"] == 3000
    assert "runAsUser: 1000" in deployment
    assert "runAsGroup: 1000" in deployment
    assert "path: /healthz" in deployment
    assert "nginx-cache" not in deployment
    assert "name: BACKEND_ORIGIN" in deployment
    assert (
        'value: "http://{{ include "university-ecosystem.fullname" . }}-backend:'
        in deployment
    )
    assert "{{ .Values.frontend.service.port }}" in network_policy
    assert "app.kubernetes.io/component: backend" in network_policy

    for compose_name in ("docker-compose.yml", "docker-compose.full.yml"):
        frontend = _compose(compose_name)["services"]["frontend"]
        assert frontend["environment"]["BACKEND_ORIGIN"] == "http://backend:8000"


def test_rendered_helm_services_and_scalers_target_real_pods() -> None:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is not installed")  # QUALITY-123 @egorribun

    command = [
        helm,
        "template",
        "contract",
        str(ROOT / "charts" / "university-ecosystem"),
        "--set",
        "redis.enabled=false",
        "--set",
        "revocationRedis.enabled=false",
        "--set",
        "nats.enabled=false",
        "--set",
        "global.imageTag=contract-sha",
        "--set",
        "gateway.config.jwtSecret=ci-placeholder",
        "--set",
        "backend.config.jwtPrivateKeyPEM=ci-placeholder",
        "--set",
        "backend.config.internalHMACSecret=ci-placeholder",
        "--set",
        "backend.config.wsHubInternalSecret=ci-placeholder",
        "--set",
        "backend.config.csrfHMACSecret=ci-placeholder",
        "--set",
        "backend.config.spotifyTokenSecret=ci-placeholder",
        "--set",
        "backend.config.elasticsearchPassword=ci-placeholder",
        "--set",
        "backend.config.spicedbPresharedKey=ci-placeholder",
        "--set",
        "backend.config.auditLogSecret=ci-placeholder",
        "--set",
        "backend.config.idempotencyHMACSecret=ci-placeholder",
        "--set",
        "fileProcessor.config.rsaPublicKeyPEM=ci-placeholder",
        "--set",
        "fileProcessor.config.minioAccessKey=ci-placeholder",
        "--set",
        "fileProcessor.config.minioSecretKey=ci-placeholder",
        "--set",
        "fileProcessor.config.temporalAPIKey=ci-placeholder",
        "--set",
        "keda.enabled=true",
        "--set",
        "hibernation.enabled=true",
        "--set",
        "ingress.enabled=true",
    ]
    rendered = subprocess.run(  # noqa: S603 - fixed Helm contract command
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    resources = [item for item in yaml.safe_load_all(rendered) if item]
    assert not any(item.get("kind") == "CronJob" for item in resources)
    migration = next(
        item
        for item in resources
        if item.get("kind") == "Job"
        and item["metadata"]["name"] == "contract-university-ecosystem-migrate"
    )
    assert migration["metadata"]["annotations"]["helm.sh/hook"] == (
        "pre-install,pre-upgrade"
    )
    migration_spec = migration["spec"]["template"]["spec"]
    assert migration_spec["automountServiceAccountToken"] is False
    migration_container = migration_spec["containers"][0]
    assert migration_container["command"] == ["alembic", "upgrade", "head"]
    assert migration_container["image"].endswith(":contract-sha")
    migration_env = {entry["name"]: entry for entry in migration_container["env"]}
    assert migration_env["DATABASE_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": "university-connections",
        "key": "database-url",
    }
    assert migration_env["ENVIRONMENT"]["value"] == "development"
    assert migration_container["securityContext"]["readOnlyRootFilesystem"] is True
    deployments = {
        item["metadata"]["name"]: item
        for item in resources
        if item.get("kind") == "Deployment"
    }
    ingress = next(item for item in resources if item.get("kind") == "Ingress")
    api_rule = next(
        rule
        for rule in ingress["spec"]["rules"]
        if rule["host"] == "api.university.example.com"
    )
    api_service = api_rule["http"]["paths"][0]["backend"]["service"]
    assert api_service["name"] == "contract-university-ecosystem-gateway"
    assert api_service["port"]["number"] == 8080

    backend = deployments["contract-university-ecosystem-backend"]
    backend_env = {
        entry["name"]: entry
        for entry in backend["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    connections_secret = "university-connections"  # pragma: allowlist secret
    assert backend_env["DATABASE_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": connections_secret,
        "key": "database-url",
    }
    assert backend_env["CACHE_REDIS_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": connections_secret,
        "key": "redis-backend-url",
    }
    assert backend_env["REVOCATION_REDIS_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": connections_secret,
        "key": "redis-revocation-url",
    }
    assert backend_env["NATS_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": connections_secret,
        "key": "nats-url",
    }
    assert backend_env["NATS_AUTH_TOKEN"]["valueFrom"]["secretKeyRef"] == {
        "name": connections_secret,
        "key": "nats-auth-token",
    }
    assert backend_env["ENVIRONMENT"]["value"] == "development"
    assert backend_env["SECRET_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "contract-secrets",
        "key": "jwt-secret",
    }
    assert backend_env["ALGORITHM"]["value"] == "RS256"
    assert backend_env["JWT_PRIVATE_KEY_PATH"]["value"] == (
        "/run/secrets/jwt-rsa-private-key.pem"
    )
    for variable, key in {
        "INTERNAL_HMAC_SECRET": "internal-hmac-secret",  # pragma: allowlist secret
        "WS_HUB_INTERNAL_SECRET": "ws-hub-internal-secret",  # pragma: allowlist secret
        "CSRF_HMAC_SECRET": "csrf-hmac-secret",  # pragma: allowlist secret
        "SPOTIFY_TOKEN_SECRET": "spotify-token-secret",  # pragma: allowlist secret
        "ELASTICSEARCH_PASSWORD": "elasticsearch-password",  # pragma: allowlist secret
        "SPICEDB_PRESHARED_KEY": "spicedb-preshared-key",
        "AUDIT_LOG_SECRET": "audit-log-secret",  # pragma: allowlist secret
        "IDEMPOTENCY_HMAC_SECRET": "idempotency-hmac-secret",  # pragma: allowlist secret
    }.items():
        assert backend_env[variable]["valueFrom"]["secretKeyRef"] == {
            "name": "contract-secrets",
            "key": key,
        }
    assert backend_env["MINIO_SECURE"]["value"] == "false"
    assert backend_env["ELASTICSEARCH_URL"]["value"] == ""
    backend_volumes = backend["spec"]["template"]["spec"]["volumes"]
    assert any(
        volume.get("secret", {}).get("secretName") == "contract-secrets"
        for volume in backend_volumes
    )
    gateway = deployments["contract-university-ecosystem-gateway"]
    gateway_env = {
        entry["name"]: entry
        for entry in gateway["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert gateway_env["REDIS_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": connections_secret,
        "key": "redis-gateway-url",
    }
    assert gateway_env["REVOCATION_REDIS_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": connections_secret,
        "key": "redis-revocation-url",
    }
    assert gateway_env["JWT_AUDIENCE"]["value"] == "university-ecosystem-api"
    assert gateway_env["VITE_ENVIRONMENT"]["value"] == "development"
    assert gateway_env["GRPC_USE_TLS"]["value"] == "false"
    assert gateway_env["OTEL_EXPORTER_OTLP_ENDPOINT"]["value"] == (
        "otel-collector:4317"
    )
    assert gateway_env["JWKS_ENDPOINT"]["value"] == (
        "http://contract-university-ecosystem-backend:8000/.well-known/jwks.json"
    )
    assert gateway_env["INTERNAL_HMAC_SECRET"]["valueFrom"]["secretKeyRef"] == {
        "name": "contract-secrets",
        "key": "internal-hmac-secret",
    }
    outbox = deployments["contract-university-ecosystem-outbox-worker"]
    outbox_env = {
        entry["name"]: entry
        for entry in outbox["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    for variable, key in {
        "DATABASE_URL": "database-url",
        "CACHE_REDIS_URL": "redis-backend-url",
        "REVOCATION_REDIS_URL": "redis-revocation-url",
        "NATS_URL": "nats-url",
        "NATS_AUTH_TOKEN": "nats-auth-token",
        "KEDA_POSTGRESQL_CONNECTION": "keda-postgresql-url",
    }.items():
        assert outbox_env[variable]["valueFrom"]["secretKeyRef"] == {
            "name": connections_secret,
            "key": key,
        }
    assert outbox_env["ENVIRONMENT"]["value"] == "development"
    assert outbox_env["SECRET_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "contract-secrets",
        "key": "jwt-secret",
    }
    for variable, key in {
        "INTERNAL_HMAC_SECRET": "internal-hmac-secret",  # pragma: allowlist secret
        "WS_HUB_INTERNAL_SECRET": "ws-hub-internal-secret",  # pragma: allowlist secret
        "CSRF_HMAC_SECRET": "csrf-hmac-secret",  # pragma: allowlist secret
        "SPOTIFY_TOKEN_SECRET": "spotify-token-secret",  # pragma: allowlist secret
        "ELASTICSEARCH_PASSWORD": "elasticsearch-password",  # pragma: allowlist secret
        "SPICEDB_PRESHARED_KEY": "spicedb-preshared-key",
        "AUDIT_LOG_SECRET": "audit-log-secret",  # pragma: allowlist secret
        "IDEMPOTENCY_HMAC_SECRET": "idempotency-hmac-secret",  # pragma: allowlist secret
    }.items():
        assert outbox_env[variable]["valueFrom"]["secretKeyRef"] == {
            "name": "contract-secrets",
            "key": key,
        }
    file_processor = deployments["contract-university-ecosystem-file-processor"]
    file_processor_env = {
        entry["name"]: entry
        for entry in file_processor["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert file_processor_env["FP_NATS_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": connections_secret,
        "key": "nats-url",
    }
    assert file_processor_env["FP_ENVIRONMENT"]["value"] == "development"
    assert file_processor_env["FP_OTLP_ENDPOINT"]["value"] == ("otel-collector:4317")
    assert file_processor_env["FP_OTLP_INSECURE"]["value"] == "true"
    assert file_processor_env["FP_TEMPORAL_TLS_DISABLED"]["value"] == "true"
    assert file_processor_env["FP_MINIO_SECURE"]["value"] == "false"

    for item in resources:
        if item.get("kind") == "Service" and (
            selector := item.get("spec", {}).get("selector", {})
        ).get("app.kubernetes.io/component"):
            assert any(
                selector.items()
                <= deployment["spec"]["template"]["metadata"]["labels"].items()
                for deployment in deployments.values()
            ), item["metadata"]["name"]
        if item.get("kind") == "ScaledObject":
            target = item["spec"]["scaleTargetRef"]
            assert target["kind"] == "Deployment"
            assert target["name"] in deployments, target["name"]

    for deployment in deployments.values():
        for container in deployment["spec"]["template"]["spec"]["containers"]:
            assert not container["image"].startswith("/"), container["image"]
            assert container["image"].endswith(":contract-sha"), container["image"]


def test_helm_supports_an_externally_managed_application_secret() -> None:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is not installed")  # QUALITY-123 @egorribun

    rendered = subprocess.run(  # noqa: S603 - fixed Helm contract command
        [
            helm,
            "template",
            "external",
            str(ROOT / "charts" / "university-ecosystem"),
            "--set",
            "redis.enabled=false",
            "--set",
            "revocationRedis.enabled=false",
            "--set",
            "nats.enabled=false",
            "--set",
            "applicationSecrets.existingSecret=managed-application-secrets",
            "--set",
            "backup.enabled=true",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    resources = [item for item in yaml.safe_load_all(rendered) if item]
    assert not any(item.get("kind") == "Secret" for item in resources)
    assert not any(
        item.get("kind") == "ConfigMap"
        and item["metadata"]["name"].endswith("-backup-scripts")
        for item in resources
    )

    backup = next(item for item in resources if item.get("kind") == "CronJob")
    pod_spec = backup["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    assert pod_spec["serviceAccountName"] == "external-backup"
    assert pod_spec["automountServiceAccountToken"] is False
    dump = pod_spec["initContainers"][0]
    upload = pod_spec["containers"][0]
    assert "pg_dump" in " ".join(dump["command"] + dump["args"])
    assert "mc cp" in " ".join(upload["command"] + upload["args"])
    dump_env = {entry["name"]: entry for entry in dump["env"]}
    assert dump_env["DATABASE_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": "university-connections",
        "key": "backup-database-url",
    }
    upload_env = {entry["name"]: entry for entry in upload["env"]}
    for variable, key in {
        "MINIO_ACCESS_KEY": "minio-access-key",
        "MINIO_SECRET_KEY": "minio-secret-key",  # pragma: allowlist secret
    }.items():
        assert upload_env[variable]["valueFrom"]["secretKeyRef"] == {
            "name": "managed-application-secrets",
            "key": key,
        }
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    for container in [dump, upload]:
        assert container["securityContext"]["readOnlyRootFilesystem"] is True
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]

    backup_policy = next(
        item
        for item in resources
        if item.get("kind") == "NetworkPolicy"
        and item["metadata"]["name"] == "external-backup-policy"
    )
    allowed_ports = {
        port["port"]
        for rule in backup_policy["spec"]["egress"]
        for port in rule.get("ports", [])
    }
    assert {53, 443, 5432, 9000} <= allowed_ports

    deployments = [item for item in resources if item.get("kind") == "Deployment"]
    secret_refs = [
        entry["valueFrom"]["secretKeyRef"]["name"]
        for deployment in deployments
        for container in deployment["spec"]["template"]["spec"]["containers"]
        for entry in container.get("env", [])
        if "valueFrom" in entry and "secretKeyRef" in entry["valueFrom"]
    ]
    assert "managed-application-secrets" in secret_refs


def test_helm_production_render_rejects_plaintext_data_planes() -> None:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is not installed")  # QUALITY-123 @egorribun

    base_command = [
        helm,
        "template",
        "production",
        str(ROOT / "charts" / "university-ecosystem"),
        "--set",
        "redis.enabled=false",
        "--set",
        "revocationRedis.enabled=false",
        "--set",
        "nats.enabled=false",
        "--set",
        "global.environment=production",
        "--set",
        "applicationSecrets.existingSecret=managed-application-secrets",
    ]
    insecure = subprocess.run(  # noqa: S603 - fixed Helm contract command
        base_command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert insecure.returncode != 0
    assert "backend.config.minioSecure=true" in insecure.stderr

    secure = subprocess.run(  # noqa: S603 - fixed Helm contract command
        [
            *base_command,
            "--set",
            "backend.config.minioSecure=true",
            "--set",
            "gateway.config.grpcUseTLS=true",
            "--set",
            "fileProcessor.config.minioSecure=true",
            "--set",
            "fileProcessor.config.temporalTLSDisabled=false",
            "--set",
            "fileProcessor.config.otlpInsecure=false",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert secure.returncode == 0, secure.stderr


def test_non_root_python_images_create_the_declared_home_directory() -> None:
    for relative_path in ("backend.Dockerfile", "Dockerfile.test"):
        dockerfile = _read(relative_path)
        useradd = next(line for line in dockerfile.splitlines() if "useradd" in line)

        assert "--home-dir /home/app" in useradd
        assert "--create-home" in useradd
        assert "--no-create-home" not in useradd


def test_caddy_plugin_dependency_is_version_pinned() -> None:
    dockerfile = _read("services/caddy/Dockerfile")

    assert "github.com/mholt/caddy-ratelimit@v0.1.0" in dockerfile
    assert not re.search(
        r"--with github\.com/mholt/caddy-ratelimit\s*$", dockerfile, re.M
    )
    for caddyfile in ("services/caddy/Caddyfile", "infrastructure/Caddyfile"):
        assert "rate_limit @ws_upgrade" in _read(caddyfile), caddyfile


def test_caddy_build_uses_matching_current_builder_and_runtime_images() -> None:
    dockerfile = _read("services/caddy/Dockerfile")
    full_caddy = _compose("docker-compose.full.yml")["services"]["caddy"]

    assert "caddy:2.11.4-builder-alpine@sha256:" in dockerfile
    assert "caddy:2.11.4-alpine@sha256:" in dockerfile
    assert "ARG CADDY_VERSION=2.11.4" in dockerfile
    assert "build" in full_caddy
    assert full_caddy["build"]["context"] == "./services/caddy"
    assert full_caddy["build"]["dockerfile"] == "Dockerfile"
    assert "image" not in full_caddy


def test_ci_caddy_smokes_use_the_pinned_project_runtime() -> None:
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / ".github" / "workflows").glob("*.yml")
    )
    runtime = (
        "caddy:2.11.4-alpine@sha256:"
        "5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648"  # pragma: allowlist secret
    )

    assert "caddy:2.11.2" not in workflows
    assert workflows.count(runtime) == 3


def test_default_caddy_config_references_only_compose_services() -> None:
    caddyfile = _read("services/caddy/Caddyfile")

    assert "frontend-stable" not in caddyfile
    assert "reverse_proxy frontend:3000" in caddyfile


def test_caddy_configs_expose_an_edge_local_health_endpoint() -> None:
    for relative_path in ("services/caddy/Caddyfile", "infrastructure/Caddyfile"):
        caddyfile = _read(relative_path)
        assert "handle /healthz" in caddyfile, relative_path
        assert 'respond "OK" 200' in caddyfile, relative_path


def test_pyroscope_image_matches_the_supported_project_version() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.observability.yml"):
        service = _compose(relative_path)["services"]["pyroscope"]
        assert (
            service["image"]
            == (
                "grafana/pyroscope:1.19.1@sha256:"
                "d5d38187f7593fdf5643ba29e67099206e8d4dee6207f78d028ea3fe621cc04d"  # pragma: allowlist secret
            )
        )


def test_base_and_full_compose_pin_the_same_valkey_minor() -> None:
    base = _compose("docker-compose.yml")["services"]["valkey"]
    full = _compose("docker-compose.full.yml")["services"]["redis"]

    assert (
        base["image"]
        == full["image"]
        == (
            "valkey/valkey:8.1-alpine@sha256:"
            "a038175878d66b9d274fbf8be73c0305e93798b83917647f167e18cef3c71eec"  # pragma: allowlist secret
        )
    )


def test_observability_stack_uses_alloy_instead_of_eol_promtail() -> None:
    services = _compose("docker-compose.observability.yml")["services"]
    alloy_config = _read("infrastructure/observability/alloy/config.alloy")

    assert "promtail" not in services
    assert (
        services["alloy"]["image"]
        == (
            "grafana/alloy:v1.18.0@sha256:"
            "491b0578c04983fd54fe99b587b6fab4404dc46d0dc16677bd6b00cc1140b308"  # pragma: allowlist secret
        )
    )
    assert services["alloy"]["read_only"] is True
    assert services["alloy"]["cap_drop"] == ["ALL"]
    assert services["alloy"]["cap_add"] == ["DAC_OVERRIDE"]
    assert "no-new-privileges:true" in services["alloy"]["security_opt"]
    assert "discovery.docker" in alloy_config
    assert "loki.source.docker" in alloy_config
    assert 'url = "http://loki:3100/loki/api/v1/push"' in alloy_config


def test_observability_override_does_not_downgrade_shared_images() -> None:
    full_services = _compose("docker-compose.full.yml")["services"]
    observability_services = _compose("docker-compose.observability.yml")["services"]

    for service in ("grafana", "prometheus", "tempo", "loki"):
        assert (
            observability_services[service]["image"] == full_services[service]["image"]
        ), service


def test_distroless_telemetry_services_use_external_health_probes() -> None:
    for relative_path in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(relative_path)["services"]

        assert "healthcheck" not in services["tempo"]
        probe = services["tempo-healthprobe"]
        assert probe["network_mode"] == "service:tempo"
        assert (
            probe["image"]
            == (
                "curlimages/curl:8.10.1@sha256:"
                "d9b4541e214bcd85196d6e92e2753ac6d0ea699f0af5741f8c6cccbfcf00ef4b"  # pragma: allowlist secret
            )
        )
        assert "http://localhost:3200/ready" in " ".join(probe["healthcheck"]["test"])


def test_observability_override_replaces_ports_and_binds_them_locally() -> None:
    source = _read("docker-compose.observability.yml")
    services = _compose("docker-compose.observability.yml")["services"]

    assert source.count("ports: !override") >= 2
    for service_name in (
        "tempo",
        "loki",
        "alloy",
        "pyroscope",
        "grafana",
        "prometheus",
    ):
        for binding in services[service_name]["ports"]:
            assert str(binding).startswith("127.0.0.1:"), (service_name, binding)


def test_only_the_caddy_edge_binds_compose_ports_on_all_interfaces() -> None:
    for path in ROOT.glob("docker-compose*.yml"):
        services = _compose(path.name).get("services", {})
        for service_name, service in services.items():
            if service_name == "caddy":
                continue
            for binding in service.get("ports", []):
                if isinstance(binding, dict):
                    assert binding.get("host_ip") == "127.0.0.1", (
                        path.name,
                        service_name,
                        binding,
                    )
                else:
                    assert str(binding).startswith("127.0.0.1:"), (
                        path.name,
                        service_name,
                        binding,
                    )


def test_infra_override_preserves_base_images_and_replaces_host_ports() -> None:
    source = _read("docker-compose.infra.yml")
    compose = yaml.safe_load(source.replace("!override", ""))
    services = compose["services"]

    assert "caddy" not in services
    assert set(services["nats"]) == {"ports"}
    assert "ports: !override" in source
    assert (
        services["elasticsearch"]["image"]
        == (_compose("docker-compose.full.yml")["services"]["elasticsearch"]["image"])
    )


def test_nightly_compose_layers_base_before_its_overrides() -> None:
    workflow = _read(".github/workflows/nightly-full-gate.yml")
    expected = (
        "docker-compose.yml:docker-compose.infra.yml:docker-compose.go.yml:"
        "docker-compose.ci-loadtest.yml"
    )

    assert workflow.count(expected) == 2
    expected_flags = (
        "-f docker-compose.yml -f docker-compose.infra.yml -f "
        "docker-compose.go.yml -f docker-compose.ci-loadtest.yml"
    )
    assert workflow.count(expected_flags) == 2
    assert (
        "docker compose -f docker-compose.yml -f docker-compose.infra.yml\n"
        "          -f docker-compose.go.yml -f docker-compose.ci-loadtest.yml"
    ) in workflow
    assert "docker-compose.infra.yml:docker-compose.go.yml:docker-compose.yml" not in (
        workflow
    )


def test_primary_ci_validates_compose_with_required_imgproxy_secrets() -> None:
    workflow = _read(".github/workflows/ci.yml")
    block = workflow[
        workflow.index(
            "- name: Validate docker compose configuration"
        ) : workflow.index("  actionlint:")
    ]

    first_config = block.index("docker compose -f docker-compose.yml config")
    assert block.index("$env:IMGPROXY_KEY") < first_config
    assert block.index("$env:IMGPROXY_SALT") < first_config
    assert (
        "docker compose -f docker-compose.yml -f docker-compose.infra.yml "
        "-f docker-compose.go.yml -f docker-compose.ci-loadtest.yml config"
    ) in block
    assert (
        "-f docker-compose.infra.yml -f docker-compose.go.yml -f docker-compose.yml"
        not in block
    )


def test_docker_context_excludes_frontend_generated_artifacts() -> None:
    expected = {
        "frontend/dist/",
        "frontend/coverage/",
        "frontend/test-results/",
        "frontend/playwright-report/",
        "frontend/.vitest/",
    }

    for relative_path in (".dockerignore", "Dockerfile.test.dockerignore"):
        patterns = {
            line.strip()
            for line in _read(relative_path).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        assert expected <= patterns


def test_protobuf_generator_uses_the_repository_go_toolchain() -> None:
    dockerfile = _read("Dockerfile.protogen")

    assert (
        (
            "golang:1.26.6-alpine3.24@sha256:"
            "af8d6740070b8906d12eae1c3e3ea0957fb63f492051ea05e354c38ef9fe88df"  # pragma: allowlist secret
        )
        in dockerfile
    )
    assert 'ARG BUF_VERSION="v1.72.0"' in dockerfile
    assert dockerfile.count("GOBIN=/usr/local/bin go install") == 3
    assert '"github.com/bufbuild/buf/cmd/buf@${BUF_VERSION}"' in dockerfile
    assert "google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.12" in dockerfile
    assert "google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.6.2" in dockerfile
    assert "buf-Linux-x86_64" not in dockerfile
    assert "curl" not in dockerfile
    assert "apk add --no-cache" in dockerfile
    assert "apt-get" not in dockerfile


def test_go_service_builders_use_the_patched_repository_toolchain() -> None:
    expected = (
        "golang:1.26.6-alpine3.24@sha256:"
        "af8d6740070b8906d12eae1c3e3ea0957fb63f492051ea05e354c38ef9fe88df"  # pragma: allowlist secret
    )

    for relative_path in (
        "services/gateway/Dockerfile",
        "services/ws-hub/Dockerfile",
        "services/file-processor/Dockerfile",
    ):
        assert expected in _read(relative_path), relative_path


def test_file_processor_sum_is_complete_for_standalone_docker_build() -> None:
    go_sum = _read("services/file-processor/go.sum")

    for module, version in (
        ("github.com/klauspost/cpuid/v2", "v2.4.0"),
        ("github.com/pelletier/go-toml/v2", "v2.4.3"),
    ):
        assert f"{module} {version} h1:" in go_sum
        assert f"{module} {version}/go.mod h1:" in go_sum


def test_file_processor_builds_health_probe_with_patched_dependencies() -> None:
    dockerfile = _read("services/file-processor/Dockerfile")
    health_probe = dockerfile[
        dockerfile.index("AS health-probe") : dockerfile.index("# Runtime stage")
    ]

    assert "GRPC_HEALTH_PROBE_VERSION=v0.4.51" in health_probe
    for dependency in (
        "github.com/spiffe/go-spiffe/v2@v2.7.0",
        "google.golang.org/grpc@v1.83.0",
        "golang.org/x/net@v0.57.0",
        "golang.org/x/text@v0.40.0",
    ):
        assert dependency in health_probe
    assert "go mod download" in health_probe
    assert "CGO_ENABLED=0 GOOS=linux go build" in health_probe
    assert "-X main.versionTag=${GRPC_HEALTH_PROBE_VERSION}" in health_probe
    assert "wget" not in health_probe
