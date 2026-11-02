#!/bin/sh
# Secrets remain out of Compose metadata and psql command-line arguments.
set -eu
set +x
LC_ALL=C
export LC_ALL

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
# libpq can fall back to terse text for client-side errors even in sqlstate
# mode. Never forward raw stderr: accept only a complete server SQLSTATE and
# retain the independently generated psql exit status. No SQL is written to disk.
collect_outcome() {
  state=UNKNOWN
  status=1
  markers=0
  while IFS= read -r record; do
    case "$record" in
      'UE_BOOTSTRAP_EXIT='*)
        code=${record#UE_BOOTSTRAP_EXIT=}
        case "$code" in
          ''|*[!0-9]*) continue ;;
        esac
        [ "${#code}" -le 3 ] && [ "$code" -le 255 ] || continue
        status=$code
        markers=$((markers + 1))
        ;;
      'psql:/bootstrap/bootstrap-app-roles.sql:'*)
        remainder=${record#psql:/bootstrap/bootstrap-app-roles.sql:}
        line=${remainder%%:*}
        case "$line" in
          ''|*[!0-9]*) continue ;;
        esac
        remainder=${remainder#"$line":}
        case "$remainder" in
          ' ERROR:  '*) candidate=${remainder#' ERROR:  '} ;;
          ' FATAL:  '*) candidate=${remainder#' FATAL:  '} ;;
          *) continue ;;
        esac
        [ "${#candidate}" -eq 5 ] || continue
        case "$candidate" in
          *[!A-Z0-9]*) continue ;;
        esac
        state=$candidate
        ;;
    esac
  done
  if [ "$markers" -ne 1 ]; then
    status=1
    state=UNKNOWN
  fi
  printf '%s %s\n' "$status" "$state"
}
outcome=$(
  {
    if psql -X --no-password -d postgres -v ON_ERROR_STOP=1 -v ECHO=none \
        -v VERBOSITY=sqlstate -v SHOW_CONTEXT=never \
        -f /bootstrap/bootstrap-from-environment.sql 2>&1 >/dev/null; then
      printf 'UE_BOOTSTRAP_EXIT=0\n'
    else
      printf 'UE_BOOTSTRAP_EXIT=%s\n' "$?"
    fi
  } | collect_outcome
)
status=${outcome%% *}
state=${outcome#* }
if [ "$status" -ne 0 ]; then
  printf '[postgres-roles-init] phase=reconcile exit=%s sqlstate=%s\n' "$status" "$state" >&2
  exit "$status"
fi
echo '[postgres-roles-init] Reconciled database roles.'
