from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
NIGHTLY = WORKFLOWS / "nightly-full-gate.yml"
MANUAL = WORKFLOWS / "manual-mutation-evidence.yml"
FULL_BACKEND = WORKFLOWS / "reusable-full-backend-mutation.yml"
HELM = WORKFLOWS / "reusable-helm-dependencies.yml"
BASELINE = ROOT / "tests" / "fixtures" / "full-backend-reusable-baseline.v4.yaml"
REQUIRED_CONTEXTS = {"CI Success", "Coverage & Quality Policy Gate"}


# The reviewed Dependabot changes are limited to these exact action references
# and their version comments. Keep the v4 fixture immutable and compare every
# remaining byte and parsed job against it.
_REVIEWED_WORKFLOW_PIN_COUNTS = {
    "nightly-full-gate.yml": (7, 4),
    "manual-mutation-evidence.yml": (5, 2),
    "reusable-full-backend-mutation.yml": (5, 5),
}
_REVIEWED_WORKFLOW_PIN_REPLACEMENTS = (
    (
        b"actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0",
        b"actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
    ),
    (
        b"astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3",
        b"astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884 # v10.3.0",
    ),
)


# AUD-346 / AUD-384 / AUD-429 nightly hunks since the frozen v4 baseline. Each
# entry maps the reviewed current bytes back to the frozen v4 bytes; the count
# is exact and the fixture itself stays untouched.
_REVIEWED_NIGHTLY_HUNKS = (
    (
        """  live-realtime-visual:
    name: Full-stand realtime and visual E2E
    if: ${{ github.ref == 'refs/heads/main' }}
    permissions:
      contents: read
    uses: ./.github/workflows/reusable-live-realtime-visual.yml

""",
        "",
    ),
    # AUD-346: reverse only the reviewed live Kind Chaos Mesh proof step.
    (
        """      - name: Run owned Kind Chaos Mesh fault and recovery proof
        timeout-minutes: 9
        run: bash scripts/chaos/aud346_live_kind_proof.sh

""",
        "",
    ),
    # AUD-347: reverse only the reviewed S3 receipt delta.
    (
        """          uv run pytest tests/chaos/ -v -m chaos --tb=short --junitxml="$RUNNER_TEMP/chaos-s3.xml"
          uv run python scripts/quality/validate_chaos_s3_junit.py "$RUNNER_TEMP/chaos-s3.xml"

      - name: Upload S3 chaos receipt
        if: ${{ success() }}
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: nightly-s3-chaos-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: ${{ runner.temp }}/chaos-s3.xml
          if-no-files-found: error

""",
        """          uv run pytest tests/chaos/ -v -m chaos --tb=short

""",
    ),
    # AUD-322: reverse only the reviewed resilience JUnit receipt delta.
    (
        """        run: |
          report="$RUNNER_TEMP/chaos-resilience.xml"
          set +e
          uv run pytest tests/chaos/ -v -m chaos --tb=short --ignore=tests/chaos/test_network_failures.py --junitxml="$report"
          pytest_status=$?
          uv run python scripts/quality/validate_chaos_resilience_junit.py "$report"
          validator_status=$?
          if [[ "$pytest_status" -ne 0 ]]; then
            exit "$pytest_status"
          fi
          exit "$validator_status"

      - name: Upload AUD-322 chaos receipt
        if: ${{ always() }}
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: nightly-chaos-resilience-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: ${{ runner.temp }}/chaos-resilience.xml
          if-no-files-found: ignore

""",
        """        run: uv run pytest tests/chaos/ -v -m chaos --tb=short

""",
    ),
    # ToxiProxy PostgreSQL latency proof. The listener line and the disposable
    # PostgreSQL step are pure additions; the Load job narrowing is in the AUD-322 entry.
    (
        """          - 9004:9004
""",
        "",
    ),
    (
        r"""      # The PostgreSQL latency proof runs in its own invocation so the
      # application's engine dials PostgreSQL through the ToxiProxy listener.
      - name: Start disposable PostgreSQL behind ToxiProxy
        shell: bash
        run: |
          set -euo pipefail
          toxiproxy_container="$(docker ps --quiet --filter publish=8474)"
          [[ "$(printf '%s\n' "$toxiproxy_container" | wc -l)" -eq 1 ]]
          mapfile -t networks < <(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$toxiproxy_container" | grep -v '^bridge$' | sed '/^$/d')
          [[ "${#networks[@]}" -eq 1 ]]
          pg_password="$(openssl rand -hex 24)"
          echo "::add-mask::${pg_password}"
          echo "CHAOS_POSTGRES_PASSWORD=${pg_password}" >> "$GITHUB_ENV"
          docker run --detach --name chaos-postgres \
            --network "${networks[0]}" --network-alias chaos-postgres \
            --env POSTGRES_USER=postgres \
            --env POSTGRES_DB=test_ecosystem \
            --env POSTGRES_PASSWORD="$pg_password" \
            pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d
          ready=""
          for _attempt in {1..60}; do
            if docker exec chaos-postgres pg_isready -h 127.0.0.1 -U postgres -d test_ecosystem >/dev/null 2>&1; then
              ready=1
              break
            fi
            sleep 2
          done
          if [[ -z "$ready" ]]; then
            docker logs --tail=80 chaos-postgres
            exit 1
          fi
          # The test fixtures create only the vector extension; the trigram index
          # that the schema declares needs pg_trgm, which the chaos job never migrates.
          docker exec chaos-postgres psql --username postgres --dbname test_ecosystem \
            --set ON_ERROR_STOP=1 \
            --command 'CREATE EXTENSION IF NOT EXISTS pg_trgm' \
            --command 'CREATE EXTENSION IF NOT EXISTS vector'

      - name: Configure ToxiProxy PostgreSQL proxy
        shell: bash
        run: |
          set -euo pipefail
          curl --fail --silent --show-error \
            --request POST http://127.0.0.1:8474/proxies \
            --header 'Content-Type: application/json' \
            --data '{"name":"postgres","listen":"0.0.0.0:9004","upstream":"chaos-postgres:5432","enabled":true}'

      - name: Run PostgreSQL latency chaos through ToxiProxy
        env:
          CHAOS_NETWORK_REQUIRED: "1"
          TOXIPROXY_URL: http://127.0.0.1:8474
        shell: bash
        run: |
          set -euo pipefail
          # 127.0.0.1 rather than localhost: localhost can resolve to ::1 first and
          # stall on Docker Desktop before falling back to IPv4.
          export DATABASE_URL="postgresql+asyncpg://postgres:${CHAOS_POSTGRES_PASSWORD}@127.0.0.1:9004/test_ecosystem"
          uv run pytest tests/chaos/test_network_failures.py -v -m chaos --tb=short

""",
        "",
    ),
    (
        "      - browser-matrix\n      - live-realtime-visual\n      - schemathesis-api-tests\n",
        "      - browser-matrix\n      - schemathesis-api-tests\n",
    ),
    (
        """      # AUD-346: dry-runs apply no faults and send no target traffic. The
      # recovery assertion is reported as NOT EVALUATED (never a pass); the
      # dry-run still validates configuration and every manifest offline.
      - name: Install uv
        uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3

      - name: Run chaos loadtest dry-runs
        run: |
          uv_python() { uv run --no-project --isolated --with pyyaml==6.0.3 python "$@"; }
          uv_python scripts/chaos/run_chaos_loadtest.py --dry-run --manifest k8s/chaos/redis-chaos.yaml --duration 5 --verbose
          uv_python scripts/chaos/run_chaos_loadtest.py --dry-run --manifest k8s/chaos/nats-chaos.yaml --duration 5
          uv_python scripts/chaos/run_chaos_loadtest.py --dry-run --manifest k8s/chaos/gateway-backend-disconnect.yaml --duration 5

""",
        """      - name: Run chaos loadtest dry-runs
        run: |
          python scripts/chaos/run_chaos_loadtest.py --dry-run --manifest k8s/chaos/redis-chaos.yaml --duration 5 --verbose
          python scripts/chaos/run_chaos_loadtest.py --dry-run --manifest k8s/chaos/nats-chaos.yaml --duration 5
          python scripts/chaos/run_chaos_loadtest.py --dry-run --manifest k8s/chaos/gateway-backend-disconnect.yaml --duration 5

""",
    ),
    (
        "      - name: Verify trusted main source\n        id: trusted_source\n",
        "      - name: Verify trusted main source\n",
    ),
    (
        """      # Runs even when the issue step failed, so a failed issue update cannot
      # silently suppress Slack; trusted-source failure still blocks both.
      - name: Detect optional Slack notification configuration
        id: slack_config
        if: ${{ !cancelled() && steps.trusted_source.outcome == 'success' }}
""",
        """      - name: Detect optional Slack notification configuration
        id: slack_config
""",
    ),
    (
        "        if: ${{ !cancelled() && steps.trusted_source.outcome == 'success' && steps.slack_config.outputs.configured == 'true' }}\n",
        "        if: ${{ steps.slack_config.outputs.configured == 'true' }}\n",
    ),
    (
        "curl --fail-with-body --silent --show-error --connect-timeout 10 --max-time 30 --output /dev/null --request POST",
        "curl --fail-with-body --silent --show-error --request POST",
    ),
)


# AUD-380: only the exact two step-local shard environment changes are
# normalized to the immutable v4 source. The original source and step digests
# still cover every other byte and every original execution step.
_REVIEWED_MUTATION_SHARD_HUNKS = {
    "manual-mutation-evidence.yml": (
        (
            """      - name: Run manual incremental mutmut (blocking, stats-derived budget)
        id: run_manual_incremental_mutmut
        if: steps.mutation_scope.outputs.has_python == 'true'
        env:
          SHARD_ID: ${{ matrix.shard }}
        run: |
""",
            """      - name: Run manual incremental mutmut (blocking, stats-derived budget)
        id: run_manual_incremental_mutmut
        if: steps.mutation_scope.outputs.has_python == 'true'
        run: |
""",
        ),
        (
            '            --shard-id "${SHARD_ID}" \\\n',
            '            --shard-id "${{ matrix.shard }}" \\\n',
        ),
        (
            '            echo "No changed mutants assigned to manual mutation '
            'shard ${SHARD_ID}/128."\n',
            '            echo "No changed mutants assigned to manual mutation '
            'shard ${{ matrix.shard }}/128."\n',
        ),
        (
            '          echo "Mutating manual shard ${SHARD_ID}/128: '
            '${#MUTANT_NAMES[@]} exact mutants"\n',
            '          echo "Mutating manual shard ${{ matrix.shard }}/128: '
            '${#MUTANT_NAMES[@]} exact mutants"\n',
        ),
    ),
    "reusable-full-backend-mutation.yml": (
        (
            """      - name: Plan and run exact full mutation shard
        id: run_full_mutmut
        env:
          SHARD_ID: ${{ matrix.shard }}
        run: |
""",
            """      - name: Plan and run exact full mutation shard
        id: run_full_mutmut
        run: |
""",
        ),
        (
            '            --shard-id "${SHARD_ID}" \\\n',
            '            --shard-id "${{ matrix.shard }}" \\\n',
        ),
        (
            "          printf -v preflight_shard_file 'shard-%02d.txt' \"${SHARD_ID}\"\n",
            "          printf -v preflight_shard_file 'shard-%02d.txt' \"${{ matrix.shard }}\"\n",
        ),
        (
            '            echo "No mutants assigned to full mutation shard ${SHARD_ID}/128."\n',
            '            echo "No mutants assigned to full mutation shard ${{ '
            'matrix.shard }}/128."\n',
        ),
        (
            '          echo "Mutating full shard ${SHARD_ID}/128: '
            '${#MUTANT_NAMES[@]} exact mutants"\n',
            '          echo "Mutating full shard ${{ matrix.shard }}/128: '
            '${#MUTANT_NAMES[@]} exact mutants"\n',
        ),
    ),
}


_GITHUB_REPOSITORY = "${{ github.repository }}"
_GITHUB_RUN_ID = "${{ github.run_id }}"
_GITHUB_RUN_ATTEMPT = "${{ github.run_attempt }}"
_GITHUB_SHA = "${{ github.sha }}"
_GITHUB_EVENT_NAME = "${{ github.event_name }}"
_GITHUB_WORKFLOW_PATH = (
    "${{ needs.verify-full-mutation-provenance.outputs.workflow_path }}"
)
_GITHUB_HELM_ARTIFACT_PREFIX = (
    "${{ needs.verify-full-mutation-provenance.outputs.helm_artifact_prefix }}"
)
_GITHUB_MUTMUT_ARTIFACT_PREFIX = (
    "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}"
    "-mutmut-generation-base-"
)
_GITHUB_ARTIFACT_NAMESPACE = (
    "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}"
)


def _yaml_mapping_nodes(node: yaml.Node) -> dict[str, tuple[yaml.Node, yaml.Node]]:
    assert isinstance(node, yaml.MappingNode)
    result: dict[str, tuple[yaml.Node, yaml.Node]] = {}
    for key_node, value_node in node.value:
        assert isinstance(key_node, yaml.ScalarNode)
        result[key_node.value] = (key_node, value_node)
    return result


def _yaml_scalar(node: yaml.Node) -> str:
    assert isinstance(node, yaml.ScalarNode)
    return node.value


def _selector_env(artifact_prefix: str) -> dict[str, str]:
    return {
        "GH_TOKEN": "${{ github.token }}",
        "REPOSITORY": _GITHUB_REPOSITORY,
        "RUN_ID": _GITHUB_RUN_ID,
        "CONSUMER_RUN_ATTEMPT": _GITHUB_RUN_ATTEMPT,
        "COMMIT_SHA": _GITHUB_SHA,
        "RUN_HEAD_SHA": _GITHUB_SHA,
        "EVENT_NAME": _GITHUB_EVENT_NAME,
        "WORKFLOW_PATH": _GITHUB_WORKFLOW_PATH,
        "ARTIFACT_PREFIX": artifact_prefix,
    }


def _reviewed_step_source_specs(name: str) -> dict[tuple[str, str], dict[str, object]]:
    if name == "nightly-full-gate.yml":
        gh_token = {"GH_TOKEN": "${{ github.token }}"}
        common = (
            (
                '--repository "$GITHUB_REPOSITORY"',
                f'--repository "{_GITHUB_REPOSITORY}"',
            ),
            ('--run-id "$GITHUB_RUN_ID"', f'--run-id "{_GITHUB_RUN_ID}"'),
            (
                '--consumer-run-attempt "$GITHUB_RUN_ATTEMPT"',
                f'--consumer-run-attempt "{_GITHUB_RUN_ATTEMPT}"',
            ),
            ('--commit-sha "$GITHUB_SHA"', f'--commit-sha "{_GITHUB_SHA}"'),
            ('--run-head-sha "$GITHUB_SHA"', f'--run-head-sha "{_GITHUB_SHA}"'),
            ('--event "$GITHUB_EVENT_NAME"', f'--event "{_GITHUB_EVENT_NAME}"'),
        )
        preflight = (
            *common,
            ('--artifact-suffix "$GITHUB_SHA"', f'--artifact-suffix "{_GITHUB_SHA}"'),
        )
        return {
            (
                "frontend-mutation-shards",
                "Select immutable same-run Stryker preflight candidate",
            ): {
                "env": gh_token,
                "remove_env": (),
                "replacements": preflight,
            },
            ("frontend-mutation-shards", "Select immutable cached shard publication"): {
                "env": {
                    **gh_token,
                    "PRODUCER_ATTEMPT": "${{ steps.validate_cached_shard.outputs.producer_attempt }}",
                    "SHARD_INDEX": "${{ matrix.shard-index }}",
                },
                "remove_env": ("SHARD_INDEX",),
                "replacements": (
                    *common,
                    (
                        '--shard-index "$SHARD_INDEX"',
                        '--shard-index "${{ matrix.shard-index }}"',
                    ),
                ),
            },
            (
                "frontend-mutation-tests-full",
                "Select immutable same-run Stryker preflight candidate",
            ): {
                "env": gh_token,
                "remove_env": (),
                "replacements": preflight,
            },
            (
                "frontend-mutation-roundtrip",
                "Select immutable same-run validated Stryker evidence candidate",
            ): {
                "env": gh_token,
                "remove_env": (),
                "replacements": common,
            },
        }
    if name == "manual-mutation-evidence.yml":
        gh_token = {"GH_TOKEN": "${{ github.token }}"}
        common = (
            (
                "--repository '${{ github.repository }}'",
                f'--repository "{_GITHUB_REPOSITORY}"',
            ),
            ("--run-id '${{ github.run_id }}'", f'--run-id "{_GITHUB_RUN_ID}"'),
            (
                "--consumer-run-attempt '${{ github.run_attempt }}'",
                f'--consumer-run-attempt "{_GITHUB_RUN_ATTEMPT}"',
            ),
            ("--commit-sha '${{ github.sha }}'", f'--commit-sha "{_GITHUB_SHA}"'),
            ("--run-head-sha '${{ github.sha }}'", f'--run-head-sha "{_GITHUB_SHA}"'),
            ("--event '${{ github.event_name }}'", f'--event "{_GITHUB_EVENT_NAME}"'),
        )
        preflight = (
            *common,
            (
                "--artifact-suffix '${{ github.sha }}'",
                f'--artifact-suffix "{_GITHUB_SHA}"',
            ),
        )
        return {
            (
                "manual-frontend-mutation-shards",
                "Select immutable same-run Stryker preflight candidate",
            ): {
                "env": gh_token,
                "remove_env": (),
                "replacements": preflight,
            },
            (
                "manual-frontend-mutation-aggregate",
                "Select immutable same-run Stryker preflight candidate",
            ): {
                "env": gh_token,
                "remove_env": (),
                "replacements": preflight,
            },
            (
                "manual-frontend-mutation-roundtrip",
                "Select immutable same-run validated Stryker evidence candidate",
            ): {
                "env": gh_token,
                "remove_env": (),
                "replacements": common,
            },
        }
    if name == "reusable-full-backend-mutation.yml":
        specs: dict[tuple[str, str], dict[str, object]] = {}
        selectors = (
            (
                "mutation-tests-full-generation-base",
                "Select same-run Helm dependency artifact",
                _GITHUB_HELM_ARTIFACT_PREFIX,
                False,
            ),
            (
                "mutation-tests-full-stats",
                "Select immutable same-run mutmut generation base",
                _GITHUB_MUTMUT_ARTIFACT_PREFIX,
                True,
            ),
            (
                "mutation-tests-full-stats",
                "Select same-run Helm dependency artifact",
                _GITHUB_HELM_ARTIFACT_PREFIX,
                False,
            ),
            (
                "mutation-tests-full-plan",
                "Select immutable same-run mutmut generation base",
                _GITHUB_MUTMUT_ARTIFACT_PREFIX,
                True,
            ),
            (
                "mutation-tests-full-plan",
                "Select same-run Helm dependency artifact",
                _GITHUB_HELM_ARTIFACT_PREFIX,
                False,
            ),
            (
                "mutation-tests-full",
                "Select immutable same-run mutmut generation base",
                _GITHUB_MUTMUT_ARTIFACT_PREFIX,
                True,
            ),
            (
                "mutation-tests-full",
                "Select same-run Helm dependency artifact",
                _GITHUB_HELM_ARTIFACT_PREFIX,
                False,
            ),
        )
        for job_id, step_name, artifact_prefix, strict in selectors:
            replacements = (
                ('--repository "$REPOSITORY"', f'--repository "{_GITHUB_REPOSITORY}"'),
                ('--run-id "$RUN_ID"', f'--run-id "{_GITHUB_RUN_ID}"'),
                (
                    '--consumer-run-attempt "$CONSUMER_RUN_ATTEMPT"',
                    f'--consumer-run-attempt "{_GITHUB_RUN_ATTEMPT}"',
                ),
                ('--commit-sha "$COMMIT_SHA"', f'--commit-sha "{_GITHUB_SHA}"'),
                ('--run-head-sha "$RUN_HEAD_SHA"', f'--run-head-sha "{_GITHUB_SHA}"'),
                ('--event "$EVENT_NAME"', f'--event "{_GITHUB_EVENT_NAME}"'),
                (
                    '--workflow-path "$WORKFLOW_PATH"',
                    f'--workflow-path "{_GITHUB_WORKFLOW_PATH}"',
                ),
                (
                    '--artifact-prefix "$ARTIFACT_PREFIX"',
                    f'--artifact-prefix "{artifact_prefix}"',
                ),
                (
                    "--attempt-policy current-or-earlier",
                    "--attempt-policy current-or-earlier",
                ),
            )
            specs[(job_id, step_name)] = {
                "env": _selector_env(artifact_prefix),
                "remove_env": (
                    "REPOSITORY",
                    "RUN_ID",
                    "CONSUMER_RUN_ATTEMPT",
                    "COMMIT_SHA",
                    "RUN_HEAD_SHA",
                    "EVENT_NAME",
                    "WORKFLOW_PATH",
                    "ARTIFACT_PREFIX",
                ),
                "replacements": replacements,
                "strict": strict,
            }
        for job_id, step_name, prefix in (
            (
                "mutation-tests-full-plan",
                "Require all full mutmut stats shards",
                "mutmut-stats",
            ),
            (
                "mutation-tests-full-aggregate",
                "Require all full mutmut execution shards",
                "mutmut-shards",
            ),
        ):
            suffix = (
                "mutmut-stats-${RUN_ID}-${RUN_ATTEMPT}-${shard}"
                if prefix == "mutmut-stats"
                else "mutmut-shard-${RUN_ID}-${RUN_ATTEMPT}-${shard}"
            )
            specs[(job_id, step_name)] = {
                "env": {
                    "RUN_ID": _GITHUB_RUN_ID,
                    "RUN_ATTEMPT": _GITHUB_RUN_ATTEMPT,
                    "ARTIFACT_NAMESPACE": _GITHUB_ARTIFACT_NAMESPACE,
                },
                "remove_env": ("ARTIFACT_NAMESPACE",),
                "strict": True,
                "replacements": (
                    (
                        f"{prefix}/${{ARTIFACT_NAMESPACE}}-{suffix}",
                        f"{prefix}/{_GITHUB_ARTIFACT_NAMESPACE}-{suffix}",
                    ),
                ),
            }
        return specs
    return {}


def _normalize_reviewed_step_sources(name: str, source: bytes) -> bytes:
    specs = _reviewed_step_source_specs(name)
    if not specs:
        return source

    root = yaml.compose(source.decode("utf-8"))
    assert root is not None
    jobs_node = _yaml_mapping_nodes(root)["jobs"][1]
    edits: list[tuple[int, int, bytes]] = []
    seen: set[tuple[str, str]] = set()

    for job_id, (_job_key, job_node) in _yaml_mapping_nodes(jobs_node).items():
        job_fields = _yaml_mapping_nodes(job_node)
        steps_entry = job_fields.get("steps")
        if steps_entry is None:
            continue
        steps_node = steps_entry[1]
        assert isinstance(steps_node, yaml.SequenceNode)
        for step_node in steps_node.value:
            fields = _yaml_mapping_nodes(step_node)
            name_field = fields.get("name")
            if name_field is None:
                continue
            identity = (job_id, _yaml_scalar(name_field[1]))
            spec = specs.get(identity)
            if spec is None:
                continue
            assert identity not in seen
            seen.add(identity)
            shell_field = fields.get("shell")
            assert shell_field is not None and _yaml_scalar(shell_field[1]) == "bash"

            env_nodes: dict[str, yaml.Node] = {}
            actual_env: dict[str, str] = {}
            env_field = fields.get("env")
            if env_field is not None:
                for key, (key_node, value_node) in _yaml_mapping_nodes(
                    env_field[1]
                ).items():
                    env_nodes[key] = key_node
                    actual_env[key] = _yaml_scalar(value_node)
            assert actual_env == spec["env"], (
                f"reviewed env mapping changed for {identity}"
            )

            run_node = fields["run"][1]
            assert isinstance(run_node, yaml.ScalarNode)
            run_text = run_node.value
            raw_run = source[run_node.start_mark.index : run_node.end_mark.index]
            default_strict = name != "reusable-full-backend-mutation.yml" or (
                "Require all full mutmut" in identity[1]
            )
            strict = bool(spec.get("strict", default_strict))
            assert run_text.startswith("set -euo pipefail\n") is strict
            for current, frozen in spec["replacements"]:
                current_bytes, frozen_bytes = (
                    current.encode("utf-8"),
                    frozen.encode("utf-8"),
                )
                assert run_text.count(current) == 1, (
                    f"reviewed argv changed for {identity}"
                )
                assert raw_run.count(current_bytes) == 1, (
                    f"reviewed run bytes changed for {identity}"
                )
                run_text = run_text.replace(current, frozen, 1)
                raw_run = raw_run.replace(current_bytes, frozen_bytes, 1)
            edits.append((run_node.start_mark.index, run_node.end_mark.index, raw_run))

            for env_key in spec["remove_env"]:
                key_node = env_nodes[env_key]
                line_start = source.rfind(b"\n", 0, key_node.start_mark.index) + 1
                line_end = source.find(b"\n", key_node.start_mark.index)
                assert line_end >= 0
                edits.append((line_start, line_end + 1, b""))

    assert seen == set(specs), (
        f"reviewed step population changed for {name}: "
        f"missing={set(specs) - seen!r}, extra={seen - set(specs)!r}"
    )
    for start, end, replacement in sorted(
        edits, key=lambda edit: edit[0], reverse=True
    ):
        source = source[:start] + replacement + source[end:]
    return source


def _normalize_reviewed_workflow_pins(name: str, source: bytes) -> bytes:
    for current, frozen in _REVIEWED_MUTATION_SHARD_HUNKS.get(name, ()):
        current_bytes, frozen_bytes = current.encode(), frozen.encode()
        assert source.count(current_bytes) == 1 and frozen_bytes not in source, (
            "reviewed mutation shard hunk changed"
        )
        source = source.replace(current_bytes, frozen_bytes, 1)
    if name == "nightly-full-gate.yml":
        for current, frozen in _REVIEWED_NIGHTLY_HUNKS:
            assert source.count(current.encode("utf-8")) == 1, (
                "reviewed nightly hunk changed"
            )
            source = source.replace(current.encode("utf-8"), frozen.encode("utf-8"), 1)
    source = _normalize_reviewed_step_sources(name, source)
    counts = _REVIEWED_WORKFLOW_PIN_COUNTS[name]
    for (current, frozen), count in zip(
        _REVIEWED_WORKFLOW_PIN_REPLACEMENTS, counts, strict=True
    ):
        assert source.count(current) == count, "reviewed action pin population changed"
        assert frozen not in source, "frozen action pin was reintroduced"
        source = source.replace(current, frozen)
    return source


def _reviewed_workflow_bytes(path: Path) -> bytes:
    source = path.read_bytes()
    # Synthetic diagnostic inputs remain raw; only the three immutable
    # repository workflow identities receive the finite reviewed transformation.
    if path in {WORKFLOWS / name for name in _REVIEWED_WORKFLOW_PIN_COUNTS}:
        return _normalize_reviewed_workflow_pins(path.name, source)
    return source


def _baseline() -> dict[str, object]:
    value = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    expected_source_keys = {
        "nightly",
        "manual",
        "reusable_full_backend_mutation",
    }
    expected_origin_source_files = {
        "nightly": "dfdf66bbb99e0f48b9e58e64da7674ae13b9a82a64524b46d73bf7351ea30666",
        "manual": "63a8c260372e99e4fb674d4f502610066fccc96bb4a04ea0913c2af04d3bb834",
        "reusable_full_backend_mutation": "dda3b12833f6f0a1e2cd9766c8e04f56bb6cc7a04f4192af56c2c8732b65d053",
    }
    assert set(value) == {
        "schema",
        "origin_commit",
        "origin_source_files",
        "source_files",
        "nightly_trigger_sha256",
        "manual_trigger_sha256",
        "nightly_preserved_jobs",
        "manual_preserved_jobs",
        "full_mutation_steps",
    }
    assert value["schema"] == "full-backend-reusable-baseline-v4"
    assert value["origin_commit"] == "cd8daacbf9aa40a7da7398750bcf0d95571edf38"
    assert set(value["origin_source_files"]) == set(expected_origin_source_files)
    assert value["origin_source_files"] == expected_origin_source_files
    assert set(value["source_files"]) == expected_source_keys
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in value["source_files"].values()
    )
    actual_source_files = {
        "nightly": hashlib.sha256(_reviewed_workflow_bytes(NIGHTLY)).hexdigest(),
        "manual": hashlib.sha256(_reviewed_workflow_bytes(MANUAL)).hexdigest(),
        "reusable_full_backend_mutation": hashlib.sha256(
            _reviewed_workflow_bytes(FULL_BACKEND)
        ).hexdigest(),
    }
    try:
        assert actual_source_files == value["source_files"]
    except AssertionError:
        _emit_binding_diagnostic()
        raise
    return value


def _digest(value: object) -> str:
    rendered = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return __import__("hashlib").sha256(rendered.encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, object]:
    value = yaml.safe_load(_reviewed_workflow_bytes(path).decode("utf-8"))
    assert isinstance(value, dict)
    return value


def _load_current(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _on(workflow: dict[str, object]) -> dict[str, object]:
    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def _jobs(workflow: dict[str, object]) -> dict[str, dict[str, object]]:
    value = workflow.get("jobs")
    assert isinstance(value, dict)
    return value


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    value = job.get("steps")
    assert isinstance(value, list)
    return value


def _step(job: dict[str, object], name: str) -> dict[str, object]:
    return next(step for step in _steps(job) if step.get("name") == name)


def _selector_run(arguments: tuple[str, ...], *, strict: bool) -> str:
    lines = ["python3 scripts/quality/select_same_run_artifact_cli.py \\"]
    lines.extend(f"  {argument} \\" for argument in arguments[:-1])
    lines.append(f"  {arguments[-1]}")
    prefix = "set -euo pipefail\n" if strict else ""
    return prefix + "\n".join(lines) + "\n"


def _assert_selector(
    step: dict[str, object],
    expected_env: dict[str, str],
    arguments: tuple[str, ...],
    *,
    strict: bool,
) -> None:
    assert step.get("shell") == "bash"
    assert step.get("env", {}) == expected_env
    assert step.get("run") == _selector_run(arguments, strict=strict)


def _assert_backend_artifact_selector(
    step: dict[str, object], artifact_prefix: str, *, strict: bool
) -> None:
    _assert_selector(
        step,
        _selector_env(artifact_prefix),
        (
            '--repository "$REPOSITORY"',
            '--run-id "$RUN_ID"',
            '--consumer-run-attempt "$CONSUMER_RUN_ATTEMPT"',
            '--commit-sha "$COMMIT_SHA"',
            '--run-head-sha "$RUN_HEAD_SHA"',
            '--event "$EVENT_NAME"',
            '--workflow-path "$WORKFLOW_PATH"',
            '--artifact-prefix "$ARTIFACT_PREFIX"',
            '--artifact-suffix ""',
            "--attempt-policy current-or-earlier",
        ),
        strict=strict,
    )


_APPROVED_ACTION_PIN_REFRESHES: dict[tuple[str, str], dict[str, tuple[str, int]]] = {
    ("nightly", "frontend-mutation-preflight"): {
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1": (
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            1,
        )
    },
    ("nightly", "frontend-mutation-shards"): {
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1": (
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            1,
        )
    },
    ("nightly", "frontend-mutation-tests-full"): {
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1": (
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            1,
        )
    },
    ("nightly", "frontend-mutation-roundtrip"): {
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1": (
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            1,
        )
    },
    ("nightly", "container-integration-cells"): {
        "astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884": (
            "astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7",
            1,
        )
    },
    ("nightly", "load-and-chaos"): {
        "astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884": (
            "astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7",
            1,
        )
    },
    ("manual", "manual-frontend-mutation-preflight"): {
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1": (
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            1,
        )
    },
    ("manual", "manual-frontend-mutation-shards"): {
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1": (
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            1,
        )
    },
    ("manual", "manual-frontend-mutation-aggregate"): {
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1": (
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            1,
        )
    },
    ("manual", "manual-frontend-mutation-roundtrip"): {
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1": (
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            1,
        )
    },
}


def _normalize_approved_action_pin_updates(
    job: dict[str, object], *, workflow_id: str, job_id: str
) -> dict[str, object]:
    expected_updates = _APPROVED_ACTION_PIN_REFRESHES.get((workflow_id, job_id))
    assert expected_updates is not None, (workflow_id, job_id)

    normalized_job = dict(job)
    normalized_steps = [dict(step) for step in _steps(job)]
    for current_ref, (frozen_ref, expected_count) in expected_updates.items():
        action_prefix = current_ref.split("@", maxsplit=1)[0] + "@"
        observed_refs = [
            step.get("uses")
            for step in normalized_steps
            if isinstance(step.get("uses"), str)
            and step["uses"].startswith(action_prefix)
        ]
        assert observed_refs == [current_ref] * expected_count, (
            workflow_id,
            job_id,
            current_ref,
            observed_refs,
        )
        assert not any(step.get("uses") == frozen_ref for step in normalized_steps)
        for step in normalized_steps:
            if step.get("uses") == current_ref:
                step["uses"] = frozen_ref

    normalized_job["steps"] = normalized_steps
    return normalized_job


def _emit_binding_diagnostic() -> None:
    """Report only the canonical current job digest after a source mismatch."""
    digest: str | None
    try:
        job = _jobs(_load(NIGHTLY))["frontend-mutation-shards"]
        assert isinstance(job, dict)
        normalized_job = _normalize_approved_action_pin_updates(
            job, workflow_id="nightly", job_id="frontend-mutation-shards"
        )
        digest = _digest(normalized_job)
    except (
        OSError,
        yaml.YAMLError,
        AssertionError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        digest = None
    payload = {
        "schema": "full-backend-binding-diagnostic-v1",
        "status": "unavailable",
    }
    if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
        payload["status"] = "available"
        payload["frontend_mutation_shards_sha256"] = digest
    if sys.stderr is None:
        return
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        sys.stderr.write(encoded + "\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        return


def _assert_preserved_job_digest(
    job: dict[str, object],
    expected_digest: str,
    *,
    workflow_id: str,
    job_id: str,
) -> None:
    key = (workflow_id, job_id)
    if key in _APPROVED_ACTION_PIN_REFRESHES:
        normalized_job = _normalize_approved_action_pin_updates(
            job, workflow_id=workflow_id, job_id=job_id
        )
    else:
        normalized_job = job
    assert _digest(normalized_job) == expected_digest


def _assert_frontend_typecheck_is_only_job_delta(
    job: dict[str, object],
    expected_digest: str,
    *,
    workflow_id: str,
    job_id: str,
) -> None:
    assert (workflow_id, job_id) in _APPROVED_ACTION_PIN_REFRESHES
    steps = _steps(job)
    typecheck_steps = [
        step
        for step in steps
        if step.get("name") == "Type-check frontend before mutation evidence"
    ]
    assert typecheck_steps == [
        {
            "name": "Type-check frontend before mutation evidence",
            "working-directory": "frontend",
            "run": "npm run typecheck",
        }
    ]

    typecheck_index = steps.index(typecheck_steps[0])
    npm_ci_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "npm ci --no-audit --no-fund"
    )
    mutation_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Generate canonical immutable Stryker preflight"
    )
    assert npm_ci_index < typecheck_index < mutation_index

    preserved_job = dict(job)
    preserved_job["steps"] = [step for step in steps if step is not typecheck_steps[0]]
    normalized_job = _normalize_approved_action_pin_updates(
        preserved_job, workflow_id=workflow_id, job_id=job_id
    )
    assert _digest(normalized_job) == expected_digest


def _assert_nightly_miri_is_only_toolchain_pin_update(
    job: dict[str, object], expected_digest: str
) -> None:
    normalized_job = dict(job)
    normalized_steps = [dict(step) for step in _steps(job)]
    toolchain_steps = [
        step
        for step in normalized_steps
        if step.get("name") == "Install nightly Rust + Miri"
    ]
    assert len(toolchain_steps) == 1
    toolchain_step = toolchain_steps[0]
    assert toolchain_step.get("uses") == (
        "dtolnay/rust-toolchain@683b588c487a69d01f6c6ddf40f036ff682cc2c8"
    )
    toolchain_step["uses"] = (
        "dtolnay/rust-toolchain@02cb101ec7c40f2c49e1d9714d64511d8e1b74de"
    )
    normalized_job["steps"] = normalized_steps
    assert _digest(normalized_job) == expected_digest


def _assert_nightly_browser_matrix_is_preserved(job: dict[str, object]) -> None:
    assert job["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert job["needs"] == "e2e-wasm-build"
    assert job["uses"] == "./.github/workflows/reusable-e2e-tests.yml"
    strategy = job["strategy"]
    assert strategy["fail-fast"] is False
    assert strategy["max-parallel"] == 2
    matrix = strategy["matrix"]["include"]
    chromium = [entry for entry in matrix if entry["browser"] == "chromium"]
    assert chromium == [
        {"browser": "chromium", "shard-index": index, "shard-total": 4}
        for index in range(1, 5)
    ]
    assert {entry["browser"] for entry in matrix if entry["browser"] != "chromium"} == {
        "firefox",
        "webkit",
        "mobile-webkit",
    }
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    assert job["with"]["node-version"] == "24"
    assert job["with"]["python-version"] == "3.14"
    assert job["with"]["collect-coverage"] == "${{ matrix.browser == 'chromium' }}"
    assert job["with"]["wasm-artifact-id"] == (
        "${{ needs.e2e-wasm-build.outputs.artifact_id }}"
    )
    assert job["with"]["wasm-artifact-name"] == (
        "${{ needs.e2e-wasm-build.outputs.artifact_name }}"
    )
    assert job["with"]["wasm-artifact-digest"] == (
        "${{ needs.e2e-wasm-build.outputs.artifact_digest }}"
    )


def _python_guard(step: dict[str, object]) -> str:
    run = step["run"]
    assert isinstance(run, str)
    match = re.fullmatch(r"python3 - <<'PY'\n(?P<program>.*)\nPY\n?", run, re.DOTALL)
    assert match is not None
    return match.group("program")


def _run_python_guard(
    program: str,
    environment: dict[str, str],
    *,
    omit_job_context: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str]:
    with tempfile.TemporaryDirectory(prefix="workflow-provenance-") as temp_dir:
        output_path = Path(temp_dir) / "github-output"
        output_path.write_text("", encoding="utf-8")
        safe_environment = {
            key: value
            for key, value in os.environ.items()
            if key.casefold() in {"path", "systemroot", "windir", "temp", "tmp"}
        }
        safe_environment.update(environment)
        safe_environment["GITHUB_OUTPUT"] = str(output_path)
        if omit_job_context:
            safe_environment.pop("JOB_CONTEXT_JSON", None)
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", program],
            check=False,
            capture_output=True,
            text=True,
            env=safe_environment,
        )
        return result, output_path.read_text(encoding="utf-8")


def _job_context(
    reusable_path: str,
    source_sha: str,
    *,
    repository: str = "egorribun/university_ecosystem",
) -> dict[str, object]:
    return {
        "workflow_ref": (f"{repository}/{reusable_path}@refs/heads/egorribun"),
        "workflow_sha": source_sha,
        "workflow_file_path": reusable_path,
        "status": "in_progress",
    }


def _base_environment(
    reusable_path: str,
    *,
    source_sha: str = "a" * 40,
    github_sha: str | None = None,
    repository: str = "egorribun/university_ecosystem",
) -> dict[str, str]:
    caller_path = ".github/workflows/manual-mutation-evidence.yml"
    return {
        "SOURCE_SHA": source_sha,
        "GITHUB_SHA_VALUE": source_sha if github_sha is None else github_sha,
        "GITHUB_REF_VALUE": "refs/heads/egorribun",
        "GITHUB_EVENT_NAME_VALUE": "workflow_dispatch",
        "GITHUB_REPOSITORY_VALUE": repository,
        "GITHUB_WORKFLOW_REF_VALUE": (
            f"{repository}/{caller_path}@refs/heads/egorribun"
        ),
        "GITHUB_WORKFLOW_SHA_VALUE": source_sha,
        "JOB_CONTEXT_JSON": json.dumps(
            _job_context(reusable_path, source_sha, repository=repository)
        ),
        "RUN_ID_VALUE": "777001",
        "RUN_ATTEMPT_VALUE": "2",
    }


def _run_provenance_guard(
    helm_artifact_name: str,
    *,
    source_sha: str = "a" * 40,
    github_sha: str | None = None,
    run_id: str = "777001",
    run_attempt: str = "2",
    job_context_json: str | None = None,
    omit_job_context: bool = False,
    repository: str = "egorribun/university_ecosystem",
) -> tuple[subprocess.CompletedProcess[str], str]:
    verify = _step(
        _jobs(_load(FULL_BACKEND))["verify-full-mutation-provenance"],
        "Validate caller, reusable source, and same-run Helm artifact",
    )
    environment = _base_environment(
        ".github/workflows/reusable-full-backend-mutation.yml",
        source_sha=source_sha,
        github_sha=github_sha,
        repository=repository,
    )
    environment["HELM_ARTIFACT_NAME"] = helm_artifact_name
    environment["RUN_ID_VALUE"] = run_id
    environment["RUN_ATTEMPT_VALUE"] = run_attempt
    if job_context_json is not None:
        environment["JOB_CONTEXT_JSON"] = job_context_json
    return _run_python_guard(
        _python_guard(verify), environment, omit_job_context=omit_job_context
    )


def _run_helm_provenance_guard(
    *,
    source_sha: str = "a" * 40,
    github_sha: str | None = None,
    job_context_json: str | None = None,
    omit_job_context: bool = False,
    repository: str = "egorribun/university_ecosystem",
) -> tuple[subprocess.CompletedProcess[str], str]:
    verify = _step(
        _jobs(_load(HELM))["produce"],
        "Verify Helm producer caller and source provenance",
    )
    environment = _base_environment(
        ".github/workflows/reusable-helm-dependencies.yml",
        source_sha=source_sha,
        github_sha=github_sha,
        repository=repository,
    )
    environment["GITHUB_EVENT_NAME_VALUE"] = "workflow_dispatch"
    if job_context_json is not None:
        environment["JOB_CONTEXT_JSON"] = job_context_json
    return _run_python_guard(
        _python_guard(verify), environment, omit_job_context=omit_job_context
    )


def _frontend_job_ids() -> tuple[str, ...]:
    return (
        "frontend-mutation-preflight",
        "frontend-mutation-shards",
        "frontend-mutation-tests-full",
        "frontend-mutation-roundtrip",
    )


def _manual_frontend_job_ids() -> tuple[str, ...]:
    return (
        "manual-frontend-mutation-preflight",
        "manual-frontend-mutation-shards",
        "manual-frontend-mutation-aggregate",
        "manual-frontend-mutation-roundtrip",
    )


def test_full_backend_is_a_trusted_reusable_workflow_with_same_run_artifacts() -> None:
    workflow = _load(FULL_BACKEND)
    call = _on(workflow)["workflow_call"]
    assert set(_on(workflow)) == {"workflow_call"}
    assert set(call["inputs"]) == {"source_sha", "helm_artifact_name"}
    assert call["inputs"]["source_sha"]["required"] is True
    assert call["inputs"]["helm_artifact_name"]["required"] is True

    jobs = _jobs(workflow)
    assert set(jobs) == {
        "verify-full-mutation-provenance",
        "mutation-tests-full-generation-base",
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full",
        "mutation-tests-full-aggregate",
    }
    verify = jobs["verify-full-mutation-provenance"]
    verify_script = _step(
        verify, "Validate caller, reusable source, and same-run Helm artifact"
    )["run"]
    verify_step = _step(
        verify, "Validate caller, reusable source, and same-run Helm artifact"
    )
    assert verify_step["env"]["JOB_CONTEXT_JSON"] == "${{ toJSON(job) }}"
    assert "${{ job.workflow_" not in verify_script
    assert 'json.loads(required_env("JOB_CONTEXT_JSON"))' in verify_script
    assert 'job_context.get("workflow_ref")' in verify_script
    assert 'job_context.get("workflow_sha")' in verify_script
    assert 'job_context.get("workflow_file_path")' in verify_script
    assert "nightly-full-gate.yml@refs/heads/main" in verify_script
    assert "manual-mutation-evidence.yml@refs/heads/egorribun" in verify_script
    assert "pull_request" not in verify_script
    assert 'if repository != "egorribun/university_ecosystem":' in verify_script
    assert 'expected_prefix = f"{helm_artifact_prefix}{run_id}-"' in verify_script
    assert "int(producer_attempt) > int(run_attempt)" in verify_script

    stats = jobs["mutation-tests-full-stats"]
    generation = jobs["mutation-tests-full-generation-base"]
    plan = jobs["mutation-tests-full-plan"]
    execute = jobs["mutation-tests-full"]
    aggregate = jobs["mutation-tests-full-aggregate"]
    assert generation["needs"] == "verify-full-mutation-provenance"
    assert stats["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-generation-base",
    ]
    assert plan["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-stats",
    ]
    assert execute["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-plan",
    ]
    assert aggregate["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full",
    ]
    assert stats["strategy"]["matrix"]["stats_shard"] == list(range(8))
    assert execute["strategy"]["matrix"]["shard"] == list(range(1, 129))
    assert execute["strategy"]["max-parallel"] == 8

    for job in (generation, stats, plan, execute, aggregate):
        for step in _steps(job):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["ref"] == "${{ github.sha }}"

    stats_upload = _step(stats, "Upload full mutmut stats shard")["with"]["name"]
    stats_download = _step(plan, "Download full mutmut stats shards")["with"]["pattern"]
    execute_upload = _step(execute, "Upload full mutation shard evidence")["with"][
        "name"
    ]
    aggregate_download = _step(aggregate, "Download full mutation shard evidence")[
        "with"
    ]["pattern"]
    for name in (stats_upload, stats_download, execute_upload, aggregate_download):
        assert (
            "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}"
            in name
        )
        assert "${{ github.run_id }}-${{ github.run_attempt }}" in name
    assert "expected=8" in _step(plan, "Require all full mutmut stats shards")["run"]
    assert "seq 0 7" in _step(plan, "Require all full mutmut stats shards")["run"]
    assert (
        "expected=128"
        in _step(aggregate, "Require all full mutmut execution shards")["run"]
    )
    assert (
        "seq 1 128"
        in _step(aggregate, "Require all full mutmut execution shards")["run"]
    )
    aggregate_script = _step(aggregate, "Merge and gate full mutation evidence")["run"]
    assert "scripts/merge_mutmut_cicd_stats.py" in aggregate_script
    assert "--expected-shards 128" in aggregate_script
    assert "scripts/check_mutation_score.py --min-score 100" in aggregate_script
    assert "if-no-artifact-found" not in str(
        _step(aggregate, "Download full mutation shard evidence")["with"]
    )


def test_full_mutmut_generation_is_retry_bound_and_reused_by_eligible_phases() -> None:
    jobs = _jobs(_load_current(FULL_BACKEND))
    generation = jobs["mutation-tests-full-generation-base"]
    assert generation["permissions"] == {"contents": "read", "actions": "read"}
    assert generation["timeout-minutes"] == 45
    assert generation["needs"] == "verify-full-mutation-provenance"
    assert (
        "--prepare-only"
        in _step(generation, "Generate reusable mutmut source and metadata")["run"]
    )
    envelope = _step(generation, "Create retry-scoped mutmut generation envelope")
    envelope_run = envelope["run"]
    assert 'test "$SOURCE_REVISION" = "$COMMIT_SHA"' in envelope_run
    assert "create-universe" in envelope_run
    assert "--mode generation" in envelope_run
    assert '"$RUN_ATTEMPT"' in envelope_run

    upload = _step(generation, "Upload full mutmut generation base")["with"]
    assert upload["name"] == (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}-"
        "mutmut-generation-base-${{ github.run_id }}-${{ github.run_attempt }}"
    )
    assert "mutmut-universe-artifact.json" in upload["path"]
    assert "mutants/" in upload["path"]
    assert upload["include-hidden-files"] is True
    assert upload["if-no-files-found"] == "error"

    plan_upload = _step(
        jobs["mutation-tests-full-plan"], "Upload preflighted full mutation plan"
    )["with"]
    assert "mutants/mutmut-universe.json" in plan_upload["path"].splitlines()

    consumers = (
        jobs["mutation-tests-full-stats"],
        jobs["mutation-tests-full-plan"],
        jobs["mutation-tests-full"],
    )
    producer_run = envelope_run
    producer_inputs = re.findall(r"--config-input ([^\s\\]+)", producer_run)
    assert producer_inputs
    for job in consumers:
        steps = _steps(job)
        selector = _step(job, "Select immutable same-run mutmut generation base")
        _assert_backend_artifact_selector(
            selector, _GITHUB_MUTMUT_ARTIFACT_PREFIX, strict=True
        )

        download = _step(job, "Download selected same-run mutmut generation base")
        assert (
            "${{ steps.select_full_mutmut_generation.outputs.artifact_id }}"
            == (download["with"]["artifact-ids"])
        )
        assert download["with"]["repository"] == "${{ github.repository }}"
        assert download["with"]["run-id"] == "${{ github.run_id }}"

        select = _step(job, "Select retry-safe full mutmut generation base")
        select_run = select["run"]
        assert "--expected-mode generation" in select_run
        assert '"$SOURCE_REVISION" = "$COMMIT_SHA"' in select_run
        assert '"$RUN_ATTEMPT"' in select_run
        assert re.findall(r"--config-input ([^\s\\]+)", select_run) == producer_inputs
        assert "mutmut-generation-selection.json" in select_run
        assert "mutants/mutmut-generation.json" in select_run
        assert any(
            step.get("name") == "Select immutable same-run mutmut generation base"
            for step in steps
        )

    stats_run = _step(
        jobs["mutation-tests-full-stats"], "Collect full mutmut stats shard"
    )["run"]
    plan_run = _step(
        jobs["mutation-tests-full-plan"],
        "Plan and budget every exact full mutation shard",
    )["run"]
    execution_run = _step(
        jobs["mutation-tests-full"], "Plan and run exact full mutation shard"
    )["run"]
    for command in (stats_run, plan_run, execution_run):
        assert "--reuse-generated-universe" in command

    mutation_commands = [
        line
        for line in execution_run.splitlines()
        if "scripts/run_mutmut_with_stats.py" in line
    ]
    assert len(mutation_commands) == 2
    assert any("--max-children 8" in command for command in mutation_commands)
    primary_command = next(
        command for command in mutation_commands if "--max-children 8" in command
    )
    confirmation_command = next(
        command for command in mutation_commands if "--max-children 2" in command
    )
    assert "--reuse-generated-universe" in primary_command
    assert "--reuse-generated-universe" not in confirmation_command


def test_full_backend_guard_rejects_input_sha_that_differs_from_event_sha() -> None:
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-1",
        source_sha="a" * 40,
        github_sha="b" * 40,
    )
    assert result.returncode != 0
    assert output == ""


def test_helm_guard_rejects_input_sha_that_differs_from_event_sha() -> None:
    result, output = _run_helm_provenance_guard(
        source_sha="a" * 40,
        github_sha="b" * 40,
    )
    assert result.returncode != 0
    assert output == ""


def test_provenance_guard_accepts_prior_helm_attempt_from_same_run() -> None:
    result, output = _run_provenance_guard("manual-full-helm-dependencies-777001-1")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert output == (
        "artifact_namespace=manual-full\n"
        "helm_artifact_prefix=manual-full-helm-dependencies-\n"
        "workflow_path=.github/workflows/manual-mutation-evidence.yml\n"
    )


def test_provenance_guard_rejects_coherent_fork_repository() -> None:
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-2",
        repository="forker/university_ecosystem",
    )
    assert result.returncode != 0
    assert output == ""
    assert "forker" not in result.stdout + result.stderr


def test_helm_provenance_guard_rejects_coherent_fork_repository() -> None:
    result, output = _run_helm_provenance_guard(
        repository="forker/university_ecosystem"
    )
    assert result.returncode != 0
    assert output == ""
    assert "forker" not in result.stdout + result.stderr


def test_provenance_guard_rejects_future_helm_attempt() -> None:
    result, output = _run_provenance_guard("manual-full-helm-dependencies-777001-3")
    assert result.returncode != 0
    assert output == ""


def test_provenance_guard_rejects_noncanonical_attempt_integer() -> None:
    result, output = _run_provenance_guard("manual-full-helm-dependencies-777001-0001")
    assert result.returncode != 0
    assert output == ""


def test_provenance_guard_rejects_helm_artifact_from_another_run() -> None:
    result, output = _run_provenance_guard("manual-full-helm-dependencies-777002-1")
    assert result.returncode != 0
    assert output == ""


def test_provenance_guard_rejects_helm_artifact_from_another_namespace() -> None:
    result, output = _run_provenance_guard("nightly-helm-dependencies-777001-1")
    assert result.returncode != 0
    assert output == ""


@pytest.mark.parametrize(
    "context_json",
    [
        "not-json",
        "[]",
        "{}",
        json.dumps(
            {
                "workflow_ref": 4,
                "workflow_sha": "a" * 40,
                "workflow_file_path": ".github/workflows/reusable-full-backend-mutation.yml",
            }
        ),
        json.dumps(
            {
                "workflow_ref": "x",
                "workflow_sha": "a" * 40,
                "workflow_file_path": ".github/workflows/reusable-full-backend-mutation.yml",
            }
        ),
    ],
)
def test_provenance_guard_rejects_missing_malformed_or_wrong_job_context(
    context_json: str,
) -> None:
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-1", job_context_json=context_json
    )
    assert result.returncode != 0
    assert output == ""
    assert "workflow_ref" not in result.stderr
    assert "workflow_sha" not in result.stderr


def test_provenance_guard_rejects_absent_job_context_without_echoing_input() -> None:
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-1", omit_job_context=True
    )
    assert result.returncode != 0
    assert output == ""
    assert "JOB_CONTEXT_JSON" not in result.stderr


def test_provenance_guard_does_not_emit_unneeded_job_context_fields() -> None:
    reusable_path = ".github/workflows/reusable-full-backend-mutation.yml"
    context = _job_context(reusable_path, "a" * 40)
    context["container"] = {"id": "DO_NOT_EMIT_CONTAINER_SENTINEL"}
    context["services"] = {"db": "DO_NOT_EMIT_SERVICE_SENTINEL"}
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-1",
        job_context_json=json.dumps(context),
    )
    assert result.returncode == 0, result.stderr
    assert "DO_NOT_EMIT" not in result.stdout + result.stderr + output


def test_helm_provenance_guard_uses_closed_job_context_and_exact_attempt() -> None:
    result, output = _run_helm_provenance_guard()
    assert result.returncode == 0, result.stderr
    assert output == (
        "artifact_name=manual-full-helm-dependencies-777001-2\n"
        "artifact_prefix=manual-full-helm-dependencies-\n"
        "workflow_path=.github/workflows/manual-mutation-evidence.yml\n"
    )
    context = _job_context(".github/workflows/reusable-helm-dependencies.yml", "a" * 40)
    context.pop("workflow_sha")
    rejected, no_output = _run_helm_provenance_guard(
        job_context_json=json.dumps(context)
    )
    assert rejected.returncode != 0
    assert no_output == ""


def test_mutation_shard_artifacts_stay_attempt_exact_and_fail_closed() -> None:
    jobs = _jobs(_load(FULL_BACKEND))
    stats = jobs["mutation-tests-full-stats"]
    plan = jobs["mutation-tests-full-plan"]
    execute = jobs["mutation-tests-full"]
    aggregate = jobs["mutation-tests-full-aggregate"]

    stats_upload = _step(stats, "Upload full mutmut stats shard")["with"]["name"]
    stats_download = _step(plan, "Download full mutmut stats shards")["with"]["pattern"]
    plan_upload = next(
        step["with"]["name"]
        for step in _steps(plan)
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    plan_download = next(
        step["with"]["name"]
        for step in _steps(execute)
        if step.get("uses", "").startswith("actions/download-artifact@")
        and "mutmut-plan" in step.get("with", {}).get("name", "")
    )
    shard_upload = _step(execute, "Upload full mutation shard evidence")["with"]["name"]
    shard_download = _step(aggregate, "Download full mutation shard evidence")["with"][
        "pattern"
    ]

    for artifact_name in (
        stats_upload,
        stats_download,
        plan_upload,
        plan_download,
        shard_upload,
        shard_download,
    ):
        assert "${{ github.run_id }}" in artifact_name
        assert "${{ github.run_attempt }}" in artifact_name
    assert "current-or-earlier" not in stats_download
    assert "current-or-earlier" not in plan_download
    assert "current-or-earlier" not in shard_download

    stats_gate = _step(plan, "Require all full mutmut stats shards")["run"]
    execution_gate = _step(aggregate, "Require all full mutmut execution shards")["run"]
    assert "expected=8" in stats_gate
    assert "seq 0 7" in stats_gate
    assert "expected=128" in execution_gate
    assert "seq 1 128" in execution_gate


def test_manual_incremental_mutation_artifacts_remain_run_attempt_bound() -> None:
    jobs = _jobs(_load(MANUAL))
    stats = jobs["manual-mutation-stats"]
    execution = jobs["manual-mutation-tests"]
    assert stats["if"] == "${{ inputs.backend_scope == 'incremental' }}"
    assert execution["if"] == "${{ inputs.backend_scope == 'incremental' }}"
    assert stats["strategy"]["matrix"]["stats_shard"] == list(range(8))
    assert execution["strategy"]["matrix"]["shard"] == list(range(1, 129))
    assert execution["needs"] == "manual-mutation-stats"

    stats_upload = _step(stats, "Upload manual mutmut stats shard")["with"]
    stats_download = _step(execution, "Download manual mutmut stats shards")["with"]
    mutation_upload = _step(execution, "Upload manual mutation evidence")["with"]
    assert stats_upload["name"] == (
        "manual-mutmut-stats-${{ github.run_id }}-${{ github.run_attempt }}-"
        "${{ matrix.stats_shard }}"
    )
    assert stats_download["pattern"] == (
        "manual-mutmut-stats-${{ github.run_id }}-${{ github.run_attempt }}-*"
    )
    assert "if-no-artifact-found" not in stats_download
    assert mutation_upload["name"] == (
        "manual-mutation-evidence-${{ github.run_id }}-${{ github.run_attempt }}-"
        "${{ matrix.shard }}"
    )
    assert "mutants/mutmut-exact-evidence/" in mutation_upload["path"]
    assert mutation_upload["if-no-files-found"] == "error"

    stats_gate = _step(execution, "Require all manual mutmut stats shards")["run"]
    assert "set -euo pipefail" in stats_gate
    assert "expected=8" in stats_gate
    assert (
        "actual=\"$(find mutmut-stats -type f -name 'mutmut-stats.json' | wc -l)\""
        in stats_gate
    )
    assert '"$actual" -ne "$expected"' in stats_gate
    assert "exit 1" in stats_gate
    assert "for shard in $(seq 0 7)" in stats_gate
    assert (
        "manual-mutmut-stats-${RUN_ID}-${RUN_ATTEMPT}-${shard}/mutmut-stats.json"
        in stats_gate
    )
    run = _step(
        execution,
        "Run manual incremental mutmut (blocking, stats-derived budget)",
    )["run"]
    assert "--num-shards 128" in run
    assert "--prepare-exact-execution" in run
    assert "--verify-exact-execution" in run
    assert "scripts/mutmut_ci_gate.py" in run
    assert "incomplete evidence is not valid" in run
    assert "continue-on-error" not in execution


def test_nightly_calls_full_backend_only_from_main_nightly_events() -> None:
    workflow = _load(NIGHTLY)
    baseline = _baseline()
    triggers = _on(workflow)
    assert set(triggers) == {"schedule", "repository_dispatch", "workflow_dispatch"}
    scheduled_triggers = {
        key: value for key, value in triggers.items() if key != "workflow_dispatch"
    }
    assert _digest(scheduled_triggers) == baseline["nightly_trigger_sha256"]
    assert triggers["workflow_dispatch"] == {}
    jobs = _jobs(workflow)
    dispatch_guard = jobs["verify-default-branch-dispatch"]
    assert dispatch_guard["if"] == "${{ github.event_name == 'workflow_dispatch' }}"
    guard_step = _step(dispatch_guard, "Require protected default branch")
    assert guard_step["env"]["WORKFLOW_REF"] == "${{ github.ref }}"
    assert '"$WORKFLOW_REF" != "refs/heads/main"' in guard_step["run"]
    assert (
        "Manual nightly checks must run from the protected main ref."
        in guard_step["run"]
    )
    assert all(
        "refs/heads/main" in str(job.get("if", ""))
        for job_id, job in jobs.items()
        if job_id != "verify-default-branch-dispatch"
    )
    assert "mutation-tests-full-stats" not in jobs
    assert "mutation-tests-full-plan" not in jobs
    assert "mutation-tests-full-aggregate" not in jobs

    helm = jobs["nightly-helm-dependencies"]
    backend = jobs["mutation-tests-full"]
    assert (
        helm["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert helm["uses"] == "./.github/workflows/reusable-helm-dependencies.yml"
    assert (
        backend["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert backend["needs"] == "nightly-helm-dependencies"
    assert backend["uses"] == "./.github/workflows/reusable-full-backend-mutation.yml"
    assert backend["with"] == {
        "source_sha": "${{ github.sha }}",
        "helm_artifact_name": "${{ needs.nightly-helm-dependencies.outputs.artifact_name }}",
    }
    notify_needs = jobs["notify-failure"]["needs"]
    assert "mutation-tests-full" in notify_needs
    assert not {
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full-aggregate",
    }.intersection(notify_needs)
    expected_jobs = baseline["nightly_preserved_jobs"]
    for job_id, expected_digest in expected_jobs.items():
        assert job_id in jobs
        if job_id == "frontend-mutation-preflight":
            _assert_frontend_typecheck_is_only_job_delta(
                jobs[job_id], expected_digest, workflow_id="nightly", job_id=job_id
            )
        elif job_id == "browser-matrix":
            _assert_nightly_browser_matrix_is_preserved(jobs[job_id])
        elif job_id == "miri":
            _assert_nightly_miri_is_only_toolchain_pin_update(
                jobs[job_id], expected_digest
            )
        else:
            _assert_preserved_job_digest(
                jobs[job_id],
                expected_digest,
                workflow_id="nightly",
                job_id=job_id,
            )


def test_manual_full_backend_is_opt_in_branch_bound_and_non_required() -> None:
    workflow = _load(MANUAL)
    baseline = _baseline()
    triggers = _on(workflow)
    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["backend_scope"] == {
        "description": "Choose the default incremental backend evidence or full backend evidence.",
        "required": True,
        "type": "choice",
        "default": "incremental",
        "options": ["incremental", "full"],
    }
    assert inputs["mutation_base_sha"]["required"] is False

    jobs = _jobs(workflow)
    for job_id in ("manual-mutation-stats", "manual-mutation-tests"):
        assert jobs[job_id]["if"] == "${{ inputs.backend_scope == 'incremental' }}"
    guard = jobs["manual-full-backend-scope-guard"]
    assert guard["if"] == "${{ inputs.backend_scope == 'full' }}"
    guard_script = _step(
        guard, "Verify manual full scope is the trusted egorribun workflow source"
    )["run"]
    assert '"$GITHUB_REF_VALUE" == "refs/heads/egorribun"' in guard_script
    assert '"$GITHUB_EVENT_NAME_VALUE" == "workflow_dispatch"' in guard_script
    assert '[[ "$GITHUB_WORKFLOW_SHA_VALUE" == "$GITHUB_SHA_VALUE" ]]' in guard_script
    assert (
        '[[ "$GITHUB_REPOSITORY_VALUE" == "egorribun/university_ecosystem" ]]'
        in guard_script
    )
    assert (
        '[[ "$GITHUB_WORKFLOW_REF_VALUE" == "egorribun/university_ecosystem/.github/workflows/manual-mutation-evidence.yml@refs/heads/egorribun" ]]'
        in guard_script
    )
    assert "$GITHUB_REPOSITORY_VALUE/.github" not in guard_script

    helm = jobs["manual-full-helm-dependencies"]
    backend = jobs["manual-full-backend-mutation"]
    assert helm["needs"] == "manual-full-backend-scope-guard"
    assert helm["uses"] == "./.github/workflows/reusable-helm-dependencies.yml"
    assert backend["needs"] == [
        "manual-full-backend-scope-guard",
        "manual-full-helm-dependencies",
    ]
    assert backend["uses"] == "./.github/workflows/reusable-full-backend-mutation.yml"
    assert backend["with"] == {
        "source_sha": "${{ github.sha }}",
        "helm_artifact_name": "${{ needs.manual-full-helm-dependencies.outputs.artifact_name }}",
    }
    for job_id in (
        "manual-full-backend-scope-guard",
        "manual-full-helm-dependencies",
        "manual-full-backend-mutation",
    ):
        assert "(non-required)" in jobs[job_id]["name"]
        assert jobs[job_id]["name"] not in REQUIRED_CONTEXTS
    expected_jobs = baseline["manual_preserved_jobs"]
    for job_id in _manual_frontend_job_ids():
        if job_id == "manual-frontend-mutation-preflight":
            _assert_frontend_typecheck_is_only_job_delta(
                jobs[job_id],
                expected_jobs[job_id],
                workflow_id="manual",
                job_id=job_id,
            )
        else:
            _assert_preserved_job_digest(
                jobs[job_id],
                expected_jobs[job_id],
                workflow_id="manual",
                job_id=job_id,
            )


def test_helm_dependency_reusable_has_fixed_callers_and_exact_run_attempt_artifact() -> (
    None
):
    workflow = _load(HELM)
    triggers = _on(workflow)
    assert set(triggers) == {"workflow_call"}
    jobs = _jobs(workflow)
    producer = jobs["produce"]
    verify = _step(producer, "Verify Helm producer caller and source provenance")
    script = verify["run"]
    assert verify["env"]["JOB_CONTEXT_JSON"] == "${{ toJSON(job) }}"
    assert "${{ job.workflow_" not in script
    assert 'json.loads(required_env("JOB_CONTEXT_JSON"))' in script
    assert 'job_context.get("workflow_ref")' in script
    assert 'job_context.get("workflow_sha")' in script
    assert 'job_context.get("workflow_file_path")' in script
    assert "nightly-full-gate.yml@refs/heads/main" in script
    assert 'if repository != "egorribun/university_ecosystem":' in script
    assert "manual-mutation-evidence.yml@refs/heads/egorribun" in script
    assert "pull_request" not in script
    upload = _step(producer, "Upload verified Helm dependency artifact")
    assert upload["with"]["name"] == "${{ steps.verify.outputs.artifact_name }}"
    artifact_script = _step(
        producer, "Verify Helm producer caller and source provenance"
    )["run"]
    assert (
        'artifact_name = f"{artifact_prefix}{run_id}-{run_attempt}"' in artifact_script
    )
    checkout = next(
        step
        for step in _steps(producer)
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "${{ github.sha }}"


def test_extraction_preserves_nightly_nonmutation_quality_lanes_and_manual_frontend() -> (
    None
):
    baseline = _baseline()
    nightly = _jobs(_load(NIGHTLY))
    expected_nightly = baseline["nightly_preserved_jobs"]
    for job_id, expected_digest in expected_nightly.items():
        assert job_id in nightly
        if job_id == "frontend-mutation-preflight":
            _assert_frontend_typecheck_is_only_job_delta(
                nightly[job_id],
                expected_digest,
                workflow_id="nightly",
                job_id=job_id,
            )
        elif job_id == "browser-matrix":
            _assert_nightly_browser_matrix_is_preserved(nightly[job_id])
        elif job_id == "miri":
            _assert_nightly_miri_is_only_toolchain_pin_update(
                nightly[job_id], expected_digest
            )
        else:
            _assert_preserved_job_digest(
                nightly[job_id],
                expected_digest,
                workflow_id="nightly",
                job_id=job_id,
            )

    manual = _jobs(_load(MANUAL))
    expected_manual = baseline["manual_preserved_jobs"]
    # The manual incremental backend lane has evolved beyond the v3 snapshot
    # with deadline-bounded execution and exact evidence validation. Its live
    # cardinality, provenance, and fail-closed contracts are pinned by the
    # focused mutation workflow tests; retain the frozen digest for the manual
    # frontend lane below.
    assert manual["manual-mutation-stats"]["if"] == (
        "${{ inputs.backend_scope == 'incremental' }}"
    )
    assert manual["manual-mutation-tests"]["if"] == (
        "${{ inputs.backend_scope == 'incremental' }}"
    )
    for job_id in _manual_frontend_job_ids():
        if job_id == "manual-frontend-mutation-preflight":
            _assert_frontend_typecheck_is_only_job_delta(
                manual[job_id],
                expected_manual[job_id],
                workflow_id="manual",
                job_id=job_id,
            )
        else:
            _assert_preserved_job_digest(
                manual[job_id],
                expected_manual[job_id],
                workflow_id="manual",
                job_id=job_id,
            )


def test_full_backend_execution_steps_match_original_except_reusable_boundaries() -> (
    None
):
    baseline = _baseline()
    reusable = _jobs(_load(FULL_BACKEND))
    expected_jobs = baseline["full_mutation_steps"]
    for job_id, expected in expected_jobs.items():
        job = reusable[job_id]
        assert job["timeout-minutes"] == expected["timeout_minutes"]
        assert _digest(job.get("strategy")) == expected["strategy_sha256"]
        expected_names = expected["step_names"]
        steps_by_name = {step.get("name"): step for step in _steps(job)}
        assert set(expected_names) <= set(steps_by_name)
        pairs = sorted(
            (name, steps_by_name[name].get("run")) for name in expected_names
        )
        assert _digest(pairs) == expected["sha256"]


def test_reusable_helm_consumer_uses_same_run_verified_artifact_before_build() -> None:
    reusable = _jobs(_load_current(FULL_BACKEND))
    provenance = _step(
        reusable["verify-full-mutation-provenance"],
        "Validate caller, reusable source, and same-run Helm artifact",
    )["run"]
    assert 'expected_prefix = f"{helm_artifact_prefix}{run_id}-"' in provenance
    assert "int(producer_attempt) > int(run_attempt)" in provenance

    for job_id in (
        "mutation-tests-full-generation-base",
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full",
    ):
        job = reusable[job_id]
        names = [step.get("name") for step in _steps(job)]
        _assert_backend_artifact_selector(
            _step(job, "Select same-run Helm dependency artifact"),
            _GITHUB_HELM_ARTIFACT_PREFIX,
            strict=False,
        )
        download = _step(job, "Download same-run Helm dependency artifact")
        assert (
            download["with"]["artifact-ids"]
            == "${{ steps.select_nightly_helm.outputs.artifact_id }}"
        )
        restore_index = names.index("Restore verified Helm dependency archives")
        build_index = names.index("Resolve Helm chart dependencies")
        assert (
            names.index("Download same-run Helm dependency artifact")
            < restore_index
            < build_index
        )
        restore = _step(job, "Restore verified Helm dependency archives")["run"]
        assert "helm_dependency_artifact.py restore" in restore
        assert "--producer-attempt-policy at-or-before" in restore
        assert '"$GITHUB_WORKSPACE" charts/university-ecosystem/charts' in restore
        helm = _step(job, "Resolve Helm chart dependencies")["run"]
        assert "--skip-refresh" in helm
        assert "helm dependency build" not in helm


def test_parser_friendly_selector_bindings_preserve_values_and_shard_checks() -> None:
    nightly = _jobs(_load_current(NIGHTLY))
    nightly_common = (
        '--repository "$GITHUB_REPOSITORY"',
        '--run-id "$GITHUB_RUN_ID"',
        '--consumer-run-attempt "$GITHUB_RUN_ATTEMPT"',
        '--commit-sha "$GITHUB_SHA"',
        '--run-head-sha "$GITHUB_SHA"',
        '--event "$GITHUB_EVENT_NAME"',
        '--workflow-path ".github/workflows/nightly-full-gate.yml"',
    )
    nightly_preflight = (
        *nightly_common,
        '--artifact-prefix "frontend-mutation-preflight-"',
        '--artifact-suffix "$GITHUB_SHA"',
        "--attempt-policy current-or-earlier",
    )
    gh_token = {"GH_TOKEN": "${{ github.token }}"}
    _assert_selector(
        _step(
            nightly["frontend-mutation-shards"],
            "Select immutable same-run Stryker preflight candidate",
        ),
        gh_token,
        nightly_preflight,
        strict=True,
    )
    _assert_selector(
        _step(
            nightly["frontend-mutation-tests-full"],
            "Select immutable same-run Stryker preflight candidate",
        ),
        gh_token,
        nightly_preflight,
        strict=True,
    )
    _assert_selector(
        _step(
            nightly["frontend-mutation-shards"],
            "Select immutable cached shard publication",
        ),
        {
            **gh_token,
            "PRODUCER_ATTEMPT": "${{ steps.validate_cached_shard.outputs.producer_attempt }}",
            "SHARD_INDEX": "${{ matrix.shard-index }}",
        },
        (
            *nightly_common,
            '--artifact-prefix "nightly-frontend-mutation-shard-"',
            '--artifact-suffix ""',
            '--producer-attempt "$PRODUCER_ATTEMPT"',
            '--shard-index "$SHARD_INDEX"',
            '--shard-count "$STRYKER_SHARD_COUNT"',
            "--attempt-policy current-or-earlier",
            "--allow-empty",
        ),
        strict=True,
    )
    _assert_selector(
        _step(
            nightly["frontend-mutation-roundtrip"],
            "Select immutable same-run validated Stryker evidence candidate",
        ),
        gh_token,
        (
            *nightly_common,
            '--artifact-prefix "frontend-mutation-validated-"',
            '--artifact-suffix ""',
            "--attempt-policy current-or-earlier",
        ),
        strict=True,
    )

    manual = _jobs(_load_current(MANUAL))
    manual_common = (
        "--repository '${{ github.repository }}'",
        "--run-id '${{ github.run_id }}'",
        "--consumer-run-attempt '${{ github.run_attempt }}'",
        "--commit-sha '${{ github.sha }}'",
        "--run-head-sha '${{ github.sha }}'",
        "--event '${{ github.event_name }}'",
        '--workflow-path ".github/workflows/manual-mutation-evidence.yml"',
    )
    manual_preflight = (
        *manual_common,
        '--artifact-prefix "frontend-mutation-preflight-"',
        "--artifact-suffix '${{ github.sha }}'",
        "--attempt-policy current-or-earlier",
    )
    _assert_selector(
        _step(
            manual["manual-frontend-mutation-shards"],
            "Select immutable same-run Stryker preflight candidate",
        ),
        gh_token,
        manual_preflight,
        strict=True,
    )
    _assert_selector(
        _step(
            manual["manual-frontend-mutation-aggregate"],
            "Select immutable same-run Stryker preflight candidate",
        ),
        gh_token,
        manual_preflight,
        strict=True,
    )
    _assert_selector(
        _step(
            manual["manual-frontend-mutation-roundtrip"],
            "Select immutable same-run validated Stryker evidence candidate",
        ),
        gh_token,
        (
            *manual_common,
            '--artifact-prefix "frontend-mutation-validated-"',
            '--artifact-suffix ""',
            "--attempt-policy current-or-earlier",
        ),
        strict=True,
    )

    full = _jobs(_load_current(FULL_BACKEND))
    for job_id in (
        "mutation-tests-full-generation-base",
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full",
    ):
        _assert_backend_artifact_selector(
            _step(full[job_id], "Select same-run Helm dependency artifact"),
            _GITHUB_HELM_ARTIFACT_PREFIX,
            strict=False,
        )
    for job_id in (
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full",
    ):
        _assert_backend_artifact_selector(
            _step(full[job_id], "Select immutable same-run mutmut generation base"),
            _GITHUB_MUTMUT_ARTIFACT_PREFIX,
            strict=True,
        )

    expected_namespace_env = {
        "RUN_ID": _GITHUB_RUN_ID,
        "RUN_ATTEMPT": _GITHUB_RUN_ATTEMPT,
        "ARTIFACT_NAMESPACE": _GITHUB_ARTIFACT_NAMESPACE,
    }
    stats = _step(
        full["mutation-tests-full-plan"], "Require all full mutmut stats shards"
    )
    assert stats["shell"] == "bash"
    assert stats["env"] == expected_namespace_env
    assert "expected=8\n" in stats["run"]
    assert "for shard in $(seq 0 7); do" in stats["run"]
    assert (
        "mutmut-stats/${ARTIFACT_NAMESPACE}-mutmut-stats-${RUN_ID}-${RUN_ATTEMPT}-${shard}/mutmut-stats.json"
        in stats["run"]
    )

    execution = _step(
        full["mutation-tests-full-aggregate"],
        "Require all full mutmut execution shards",
    )
    assert execution["shell"] == "bash"
    assert execution["env"] == expected_namespace_env
    assert "expected=128\n" in execution["run"]
    assert "for shard in $(seq 1 128); do" in execution["run"]
    assert (
        "mutmut-shards/${ARTIFACT_NAMESPACE}-mutmut-shard-${RUN_ID}-${RUN_ATTEMPT}-${shard}/mutmut-cicd-stats.json"
        in execution["run"]
    )


def _replace_step_block_source(
    source: bytes,
    job_id: str,
    step_name: str,
    current: bytes,
    replacement: bytes,
) -> bytes:
    job_marker = f"  {job_id}:\n".encode()
    step_marker = f"      - name: {step_name}\n".encode()
    job_start = source.find(job_marker)
    assert job_start >= 0
    step_start = source.find(step_marker, job_start)
    assert step_start >= 0
    next_step = source.find(b"      - name: ", step_start + len(step_marker))
    step_end = len(source) if next_step < 0 else next_step
    step_source = source[step_start:step_end]
    assert step_source.count(current) == 1
    return (
        source[:step_start]
        + step_source.replace(current, replacement, 1)
        + source[step_end:]
    )


@pytest.mark.parametrize(
    ("current", "replacement", "failure"),
    [
        (
            b"RUN_ID: ${{ github.run_id }}",
            b"RUN_ID: ${{ github.run_attempt }}",
            "reviewed env mapping changed",
        ),
        (
            b"--attempt-policy current-or-earlier",
            b"--attempt-policy all",
            "reviewed argv changed",
        ),
    ],
    ids=["wrong-run-id-env", "wrong-attempt-policy-argv"],
)
def test_selector_source_normalizer_rejects_env_and_argv_drift(
    current: bytes, replacement: bytes, failure: str
) -> None:
    source = bytes(FULL_BACKEND.read_bytes())
    changed = _replace_step_block_source(
        source,
        "mutation-tests-full-generation-base",
        "Select same-run Helm dependency artifact",
        current,
        replacement,
    )
    with pytest.raises(AssertionError, match=failure):
        _normalize_reviewed_step_sources(FULL_BACKEND.name, changed)


def _binding_diagnostic_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, str, str, str]:
    updates = _APPROVED_ACTION_PIN_REFRESHES[("nightly", "frontend-mutation-shards")]
    assert len(updates) == 1
    current_ref, (frozen_ref, count) = next(iter(updates.items()))
    assert count == 1
    path = tmp_path / "nightly.yml"
    monkeypatch.setitem(globals(), "NIGHTLY", path)
    canary = "opaque-π-" + os.urandom(12).hex()
    return path, canary, current_ref, frozen_ref


@pytest.mark.parametrize("delta", ["unchanged", "added", "removed", "modified"])
def test_binding_diagnostic_reports_exact_current_job_without_raw_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    delta: str,
) -> None:
    path, canary, current_ref, frozen_ref = _binding_diagnostic_input(
        monkeypatch, tmp_path
    )
    job = {"name": canary, "steps": [{"uses": current_ref}, {"run": "true"}]}
    expected = {"name": canary, "steps": [{"uses": frozen_ref}, {"run": "true"}]}
    if delta == "added":
        job["steps"].append({"run": "printf added"})
        expected["steps"].append({"run": "printf added"})
    elif delta == "removed":
        job["steps"].pop()
        expected["steps"].pop()
    elif delta == "modified":
        job["steps"][1]["run"] = "printf changed"
        expected["steps"][1]["run"] = "printf changed"
    path.write_text(
        json.dumps({"jobs": {"frontend-mutation-shards": job}}), encoding="utf-8"
    )
    before = path.read_bytes()
    with pytest.raises(AssertionError) as caught:
        _baseline()
    assert caught.traceback[-1].frame.code.name == "_baseline"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    expected_digest = hashlib.sha256(
        json.dumps(
            expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    assert json.loads(captured.err) == {
        "schema": "full-backend-binding-diagnostic-v1",
        "status": "available",
        "frontend_mutation_shards_sha256": expected_digest,
    }
    assert len(captured.err) < 256
    assert canary not in captured.err
    assert canary not in str(caught.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "defect",
    [
        "yaml",
        "missing-job",
        "bad-job",
        "bad-steps",
        "missing-pin",
        "duplicate-pin",
        "foreign-pin",
        "frozen-pin",
        "read-error",
        "decode-error",
        "digest-error",
        "nonhex-digest",
        "uppercase-digest",
        "short-digest",
        "long-digest",
        "nonstring-digest",
    ],
)
def test_binding_diagnostic_unavailable_preserves_the_original_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    defect: str,
) -> None:
    path, canary, current_ref, frozen_ref = _binding_diagnostic_input(
        monkeypatch, tmp_path
    )
    job = {"name": canary, "steps": [{"uses": current_ref}]}
    workflow = {"jobs": {"frontend-mutation-shards": job}}
    if defect == "missing-job":
        workflow["jobs"].clear()
    elif defect == "bad-job":
        workflow["jobs"]["frontend-mutation-shards"] = canary
    elif defect == "bad-steps":
        job["steps"] = None
    elif defect == "missing-pin":
        job["steps"].clear()
    elif defect == "duplicate-pin":
        job["steps"].append({"uses": current_ref})
    elif defect == "foreign-pin":
        job["steps"][0]["uses"] = current_ref.split("@")[0] + "@" + canary
    elif defect == "frozen-pin":
        job["steps"][0]["uses"] = frozen_ref
    path.write_text(json.dumps(workflow), encoding="utf-8")
    if defect == "yaml":
        path.write_text("jobs: [" + canary, encoding="utf-8")
    elif defect == "decode-error":
        path.write_bytes(b"\xff" + canary.encode("utf-8"))
    elif defect == "read-error":

        def fail_read(_path: Path) -> dict[str, object]:
            raise OSError(canary)

        monkeypatch.setitem(globals(), "_load", fail_read)
    elif defect == "digest-error":

        def fail_digest(_value: object) -> str:
            raise ValueError(canary)

        monkeypatch.setitem(globals(), "_digest", fail_digest)
    elif defect.endswith("-digest"):
        invalid_digest = {
            "nonhex-digest": canary,
            "uppercase-digest": "F" * 64,
            "short-digest": "a" * 63,
            "long-digest": "a" * 65,
            "nonstring-digest": True,
        }[defect]
        monkeypatch.setitem(globals(), "_digest", lambda _value: invalid_digest)
    with pytest.raises(AssertionError) as caught:
        _baseline()
    assert caught.traceback[-1].frame.code.name == "_baseline"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert json.loads(captured.err) == {
        "schema": "full-backend-binding-diagnostic-v1",
        "status": "unavailable",
    }
    assert len(captured.err) < 256
    assert canary not in captured.err
    assert canary not in str(caught.value)


@pytest.mark.parametrize("case", ["matching-source", "invalid-origin"])
def test_binding_diagnostic_does_not_run_outside_the_source_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: str,
) -> None:
    value = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    value["source_files"] = {
        "nightly": hashlib.sha256(_reviewed_workflow_bytes(NIGHTLY)).hexdigest(),
        "manual": hashlib.sha256(_reviewed_workflow_bytes(MANUAL)).hexdigest(),
        "reusable_full_backend_mutation": hashlib.sha256(
            _reviewed_workflow_bytes(FULL_BACKEND)
        ).hexdigest(),
    }
    if case == "invalid-origin":
        value["origin_commit"] = "not-the-reviewed-origin"
    path = tmp_path / "baseline.yaml"
    path.write_text(yaml.safe_dump(value), encoding="utf-8")
    monkeypatch.setitem(globals(), "BASELINE", path)
    if case == "matching-source":
        assert _baseline() == value
    else:
        with pytest.raises(AssertionError) as caught:
            _baseline()
        assert caught.traceback[-1].frame.code.name == "_baseline"
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("error_type", [OSError, ValueError])
def test_binding_diagnostic_output_failure_does_not_replace_the_assertion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error_type: type[Exception]
) -> None:
    path, canary, current_ref, _ = _binding_diagnostic_input(monkeypatch, tmp_path)
    path.write_text(
        json.dumps(
            {
                "jobs": {
                    "frontend-mutation-shards": {
                        "name": canary,
                        "steps": [{"uses": current_ref}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    class UnavailableStderr:
        def write(self, _value: str) -> int:
            raise error_type(canary)

    with monkeypatch.context() as context:
        context.setattr(sys, "stderr", UnavailableStderr())
        with pytest.raises(AssertionError) as caught:
            _baseline()
    assert caught.traceback[-1].frame.code.name == "_baseline"
    assert canary not in str(caught.value)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


@pytest.mark.parametrize(
    "name, identity",
    [
        ("nightly-full-gate.yml", "nightly"),
        ("manual-mutation-evidence.yml", "manual"),
        ("reusable-full-backend-mutation.yml", "reusable_full_backend_mutation"),
    ],
)
@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "unapproved", "frozen", "unrelated", "comment"]
)
def test_reviewed_action_pin_refresh_accepts_no_other_source_change(
    name: str, identity: str, mutation: str
) -> None:
    source = (WORKFLOWS / name).read_bytes()
    expected = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))["source_files"][
        identity
    ]
    assert (
        hashlib.sha256(_normalize_reviewed_workflow_pins(name, source)).hexdigest()
        == expected
    )
    current, frozen = _REVIEWED_WORKFLOW_PIN_REPLACEMENTS[0]
    if mutation == "missing":
        changed = source.replace(current, b"", 1)
    elif mutation == "duplicate":
        changed = source + b"\n# " + current + b"\n"
    elif mutation == "unapproved":
        changed = source.replace(current, current.replace(b"@6", b"@7", 1), 1)
    elif mutation == "frozen":
        changed = source.replace(current, frozen, 1)
    elif mutation == "comment":
        changed = source.replace(current, current.replace(b"v7.1.0", b"v7.1.1"), 1)
    else:
        changed = source + b"\npermissions: write-all\n"
    with pytest.raises(AssertionError):
        normalized = _normalize_reviewed_workflow_pins(name, changed)
        assert hashlib.sha256(normalized).hexdigest() == expected


@pytest.mark.parametrize("index", range(len(_REVIEWED_NIGHTLY_HUNKS)))
def test_reviewed_nightly_hunks_accept_only_exact_current_bytes(index: int) -> None:
    current, _frozen = _REVIEWED_NIGHTLY_HUNKS[index]
    source = NIGHTLY.read_bytes()
    assert source.count(current.encode("utf-8")) == 1
    drifted = source.replace(current.encode("utf-8"), b"# drifted reviewed hunk\n", 1)
    with pytest.raises(AssertionError, match="reviewed nightly hunk changed"):
        _normalize_reviewed_workflow_pins(NIGHTLY.name, drifted)


def test_load_and_chaos_writes_and_validates_junit_even_on_failure() -> None:
    job = _jobs(yaml.safe_load(NIGHTLY.read_text(encoding="utf-8")))["load-and-chaos"]
    assert job["name"] == "Load and chaos resilience"
    assert job["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert job.get("needs", []) == []

    steps = job["steps"]
    pytest_step = next(
        step for step in steps if step.get("name") == "Run chaos and resilience tests"
    )
    upload = next(
        step for step in steps if step.get("name") == "Upload AUD-322 chaos receipt"
    )
    run = pytest_step["run"]
    assert 'report="$RUNNER_TEMP/chaos-resilience.xml"' in run
    assert "set +e" in run
    # The PostgreSQL proof needs ToxiProxy, which this job does not run, so
    # its module is excluded here instead of being skipped into a failing report.
    assert (
        "uv run pytest tests/chaos/ -v -m chaos --tb=short"
        " --ignore=tests/chaos/test_network_failures.py"
        ' --junitxml="$report"' in run
    )
    assert "pytest_status=$?" in run
    assert (
        'uv run python scripts/quality/validate_chaos_resilience_junit.py "$report"'
        in run
    )
    assert "validator_status=$?" in run
    assert (
        run.index("pytest_status=$?")
        < run.index("validate_chaos_resilience_junit.py")
        < run.index("validator_status=$?")
    )
    assert 'if [[ "$pytest_status" -ne 0 ]]; then' in run
    assert 'exit "$pytest_status"' in run
    assert 'exit "$validator_status"' in run
    assert run.index('exit "$pytest_status"') < run.index('exit "$validator_status"')
    assert pytest_step.get("continue-on-error", False) is False

    assert upload["if"] == "${{ always() }}"
    assert upload["uses"] == (
        "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
    )
    assert upload["with"]["name"] == (
        "nightly-chaos-resilience-${{ github.sha }}-${{ github.run_id }}-"
        "${{ github.run_attempt }}"
    )
    assert upload["with"]["path"] == "${{ runner.temp }}/chaos-resilience.xml"
    assert upload["with"]["if-no-files-found"] == "ignore"
    # Keep the workflow's configured default artifact retention for this report.
    assert "retention-days" not in upload["with"]


# AUD-346: the chaos dry-run gate must never be satisfied by a fake target.
# These checks parse the job and assert behaviour instead of workflow bytes.
_CHAOS_SCRIPT_MARKER = "run_chaos_loadtest.py"


def _live_chaos_job() -> dict[str, object]:
    return _jobs(yaml.safe_load(NIGHTLY.read_text(encoding="utf-8")))[
        "chaos-loadtest-orchestrator"
    ]


def _chaos_dry_run_violations(job: dict[str, object]) -> list[str]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return ["job has no steps"]
    violations: list[str] = []
    invocations = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = str(step.get("name", ""))
        run = str(step.get("run", ""))
        if "http.server" in run or "dry-run health target" in name.lower():
            violations.append(f"local fake target step: {name}")
        for line in run.splitlines():
            if _CHAOS_SCRIPT_MARKER not in line:
                continue
            invocations += 1
            if "--dry-run" not in line:
                violations.append(f"live invocation in dry-run gate: {line.strip()}")
            if "--target-url" in line or "8000" in line:
                violations.append(f"dry-run target override: {line.strip()}")
    if invocations == 0:
        violations.append("no chaos dry-run invocation")
    return violations


def test_nightly_chaos_dry_run_gate_has_no_fake_target() -> None:
    job = _live_chaos_job()

    assert _chaos_dry_run_violations(job) == []


@pytest.mark.parametrize(
    "mutation", ["fake_target", "live", "target_override", "absent"]
)
def test_chaos_dry_run_gate_checker_rejects_fake_or_live_gates(mutation: str) -> None:
    job = copy.deepcopy(_live_chaos_job())
    steps = job["steps"]
    assert isinstance(steps, list)
    dry_index = next(
        index
        for index, step in enumerate(steps)
        if isinstance(step, dict) and _CHAOS_SCRIPT_MARKER in str(step.get("run", ""))
    )
    if mutation == "fake_target":
        steps.insert(
            0,
            {
                "name": "Start local dry-run health target",
                "run": "python3 -m http.server 8000 --bind 127.0.0.1",
            },
        )
    elif mutation == "live":
        steps[dry_index]["run"] = steps[dry_index]["run"].replace("--dry-run ", "", 1)
    elif mutation == "target_override":
        steps[dry_index]["run"] += (
            "\npython scripts/chaos/run_chaos_loadtest.py --dry-run "
            "--target-url http://127.0.0.1:8000/health\n"
        )
    else:
        del steps[dry_index]

    assert _chaos_dry_run_violations(job) != []


@pytest.mark.parametrize(
    ("name", "index"),
    [
        (name, index)
        for name, hunks in _REVIEWED_MUTATION_SHARD_HUNKS.items()
        for index in range(len(hunks))
    ],
)
@pytest.mark.parametrize("defect", ["missing", "duplicate", "reverted", "modified"])
def test_reviewed_mutation_shard_hunks_accept_only_exact_current_bytes(
    name: str, index: int, defect: str
) -> None:
    current, frozen = _REVIEWED_MUTATION_SHARD_HUNKS[name][index]
    current_bytes, frozen_bytes = current.encode("utf-8"), frozen.encode("utf-8")
    source = (WORKFLOWS / name).read_bytes()
    assert source.count(current_bytes) == 1
    if defect == "missing":
        changed = source.replace(current_bytes, b"", 1)
    elif defect == "duplicate":
        changed = source + current_bytes
    elif defect == "reverted":
        changed = source.replace(current_bytes, frozen_bytes, 1)
    else:
        changed = source.replace(
            current_bytes, current_bytes.replace(b"SHARD_ID", b"OTHER_ID", 1), 1
        )
    with pytest.raises(AssertionError, match="reviewed mutation shard hunk changed"):
        _normalize_reviewed_workflow_pins(name, changed)


@pytest.mark.parametrize("name", list(_REVIEWED_MUTATION_SHARD_HUNKS))
def test_reviewed_mutation_shard_hunks_do_not_allow_other_source_changes(
    name: str,
) -> None:
    identity = (
        "manual"
        if name == "manual-mutation-evidence.yml"
        else "reusable_full_backend_mutation"
    )
    source = (WORKFLOWS / name).read_bytes()
    current = b"--max-timeout-seconds 20970"
    assert current in source
    changed = source.replace(current, b"--max-timeout-seconds 20969", 1)
    normalized = _normalize_reviewed_workflow_pins(name, changed)
    baseline = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    assert hashlib.sha256(normalized).hexdigest() != baseline["source_files"][identity]


def test_reviewed_full_shard_step_digest_rejects_other_run_changes() -> None:
    baseline = _baseline()
    expected = baseline["full_mutation_steps"]["mutation-tests-full"]
    source = FULL_BACKEND.read_bytes()
    current = (
        b'            --shard-id "${SHARD_ID}" \\\n'
        b"            --num-shards 128 \\\n"
        b"            --max-children 8 \\\n"
    )
    assert source.count(current) == 1
    changed = source.replace(current, current.replace(b"128", b"127", 1), 1)
    normalized = _normalize_reviewed_workflow_pins(FULL_BACKEND.name, changed)
    workflow = _jobs(yaml.safe_load(normalized))
    steps = {step.get("name"): step for step in _steps(workflow["mutation-tests-full"])}
    pairs = sorted((name, steps[name].get("run")) for name in expected["step_names"])
    assert _digest(pairs) != expected["sha256"]
