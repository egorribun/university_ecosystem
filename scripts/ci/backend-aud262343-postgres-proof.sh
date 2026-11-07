#!/usr/bin/env bash
set -euo pipefail
probe_root="$(mktemp -d "$RUNNER_TEMP/aud262343-postgres.XXXXXX")"
trap 'rm -rf -- "$probe_root"' EXIT
pytest_status=0
aud262343_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
uv run --frozen --no-sync pytest \
  tests/test_aud262_postcommit_redis_failure.py \
  tests/test_chat_idempotency_ownership.py::test_simultaneous_dispatchers_persist_one_real_message \
  tests/integration/test_aud343_notification_fallback_postgres.py \
  -n 0 -v --tb=short --show-capture=no --no-cov --maxfail=0 \
  -p no:cacheprovider --junitxml="$probe_root/junit.xml" \
  --basetemp="$probe_root/basetemp" \
  > "$probe_root/pytest.log" 2>&1 || pytest_status=$?
tail -n 160 "$probe_root/pytest.log"
if ! uv run --frozen --no-sync python -I \
  "$aud262343_script_dir/validate_aud262343_postgres_junit.py" \
  "$probe_root/junit.xml"
then
  [ "$pytest_status" -ne 0 ] || pytest_status=1
fi
exit "$pytest_status"
