#!/bin/sh
# Secrets remain out of Compose metadata and psql command-line arguments.
set -eu
set +x

load_secret() {
    name=$1
    eval 'value=${'"$name"'-}'
    eval 'source=${'"$name"'_FILE-}'
    if [ -n "$source" ]; then
        [ -z "$value" ] || { echo 'Conflicting database credential sources' >&2; exit 1; }
        [ -f "$source" ] && [ -r "$source" ] || { echo 'Unreadable database credential source' >&2; exit 1; }
        value=$(cat "$source")
    fi
    [ -n "$value" ] || { echo 'Missing database credential' >&2; exit 1; }
    export "$name=$value"
}
load_secret PGPASSWORD
load_secret UE_MIGRATOR_DB_PASSWORD
load_secret UE_APP_DB_PASSWORD
load_secret UE_WORKER_DB_PASSWORD
: "${POSTGRES_DB:?Missing database name}"
export POSTGRES_DB
# Establish logging controls at session startup, before transaction sampling.
PGOPTIONS='-c log_statement=none -c log_min_error_statement=panic -c log_min_duration_statement=-1 -c log_min_duration_sample=-1 -c log_transaction_sample_rate=0 -c log_parameter_max_length_on_error=0'
export PGOPTIONS
# Do not expose SQL error contexts containing interpolated role passwords.
# The SQL transaction separately suppresses server-side statement logging.
if ! psql -X --no-password -d postgres -v ON_ERROR_STOP=1 -v ECHO=none \
    -f /bootstrap/bootstrap-from-environment.sql >/dev/null 2>&1; then
    echo '[postgres-roles-init] Bootstrap failed; no credential-bearing diagnostics emitted.' >&2
    exit 1
fi
echo '[postgres-roles-init] Reconciled database roles.'
