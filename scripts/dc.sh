#!/usr/bin/env sh
# scripts/dc.sh — Docker Compose wrapper that always resolves to the git repo
# root regardless of caller cwd.
#
# Mitigates W169 (z) #1: `docker compose -f docker-compose.full.yml ...` is
# path-sensitive. Bash cwd drift from `cd subdir && ...` chains caused silent
# failure during Wave 169 SW4 (compose exited 0 with no rebuild because the
# compose file was looked up relative to the drifted cwd `frontend/`). This
# wrapper ALWAYS resolves to the git repo root via `git rev-parse --show-toplevel`
# so cwd cannot drift the invocation.
#
# Usage examples:
#   bash scripts/dc.sh up -d --build frontend
#   bash scripts/dc.sh ps
#   bash scripts/dc.sh logs -f backend
#   bash scripts/dc.sh exec frontend sh -c 'ls -la /app/dist/client/assets'
#
# Compose topology overrides and destructive volume removal are deliberately
# unavailable here; use start-docker.ps1 (-ExtraCompose) for other topologies.
# Storage-starting commands share the launcher's legacy MinIO volume guard
# (ADR-042, docs/runbooks/s3-seaweedfs-cutover.md).
#
# Cross-reference: CLAUDE.md ## Gotchas "Docker compose helper scripts" + the
# pre-existing W169 SW6-followup entry "`docker compose` exit code NOT a
# reliable success signal — cwd drift causes silent failure".

set -e

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$ROOT" ]; then
  echo "scripts/dc.sh: ERROR — not in a git repository. Aborting." >&2
  exit 1
fi

cd "$ROOT"
ENV_FILE="$ROOT/.env.docker"
if [ ! -f "$ENV_FILE" ]; then
  echo "scripts/dc.sh: ERROR — .env.docker is missing. Run ./start-docker.ps1 once to generate it." >&2
  exit 1
fi

# Never let an `up` (including one scoped to another service) create empty
# SeaweedFS storage next to an unmigrated legacy MinIO volume. Keep read-only
# inspection and shutdown commands available for recovery.
guard_required=1
compose_command=
compose_command_index=0
expect_project=0
argument_index=0
for argument do
  argument_index=$((argument_index + 1))
  case "$argument" in
    -f*|-p?*|--file|--file=*|--project-directory|--project-directory=*|--env-file|--env-file=*)
      echo "scripts/dc.sh: Compose topology overrides are not supported; use start-docker.ps1 -ExtraCompose." >&2
      exit 2 ;;
  esac
  if [ "$expect_project" -eq 1 ]; then
    expect_project=0
    continue
  fi
  case "$argument" in
    -p|--project-name) expect_project=1 ;;
    --project-name=*) ;;
    -*)
      echo "scripts/dc.sh: Unsupported global Compose option; refusing an unreviewed command shape." >&2
      exit 2 ;;
    *) compose_command=$argument; compose_command_index=$argument_index; break ;;
  esac
done
exec_payload_start=0
if [ "$compose_command" = exec ]; then
  service_position=$((compose_command_index + 1))
  program_position=$((compose_command_index + 2))
  argument_index=0
  exec_service=
  exec_program=
  for argument do
    argument_index=$((argument_index + 1))
    [ "$argument_index" -eq "$service_position" ] && exec_service=$argument
    [ "$argument_index" -eq "$program_position" ] && exec_program=$argument
  done
  if [ -n "$exec_service" ] && [ -n "$exec_program" ]; then
    case "$exec_service:$exec_program" in
      -*|*:-*) ;;
      *) exec_payload_start=$((compose_command_index + 3)) ;;
    esac
  fi
fi
argument_index=0
for argument do
  argument_index=$((argument_index + 1))
  if [ "$exec_payload_start" -gt 0 ] && [ "$argument_index" -ge "$exec_payload_start" ]; then
    break
  fi
  case "$argument" in
    --file|--file=*|--project-directory|--project-directory=*|--env-file|--env-file=*)
      echo "scripts/dc.sh: Compose topology overrides are not supported; use start-docker.ps1 -ExtraCompose." >&2
      exit 2 ;;
    -f*)
      case "$compose_command" in
        logs|exec) ;;
        *)
          echo "scripts/dc.sh: Compose topology overrides are not supported; use start-docker.ps1 -ExtraCompose." >&2
          exit 2 ;;
      esac ;;
  esac
done
case "$compose_command" in
  ps|logs|config|stop|images|top|ls|version|events|port) guard_required=0 ;;
  down)
    guard_required=0
    for argument do
      case "$argument" in
        -v|-v=*|--volume|--volume=*|--volumes|--volumes=*)
          echo "scripts/dc.sh: Refusing destructive Compose down --volumes; use a separately reviewed data cleanup procedure." >&2
          exit 2 ;;
      esac
    done
    ;;
esac
if [ "$guard_required" -eq 1 ]; then
    # Same rule as start-docker.ps1 Assert-LegacyS3VolumeGuard.
    project=${COMPOSE_PROJECT_NAME:-}
    carriage_return=$(printf '\r')
    if [ -z "$project" ]; then
      while IFS='=' read -r key value; do
        if [ "$key" = COMPOSE_PROJECT_NAME ]; then
          # Tolerate a CRLF env file written on Windows.
          project=${value%"$carriage_return"}
        fi
      done < "$ENV_FILE"
      # Compose accepts quoted env-file values; remove one matching pair.
      case "$project" in
        \"*\") project=${project#\"}; project=${project%\"} ;;
        \'*\') project=${project#\'}; project=${project%\'} ;;
      esac
    fi
    if [ -z "$project" ]; then
      project=university_ecosystem
    fi
    previous=
    for argument do
      case "$previous" in
        -p|--project-name) project=$argument; previous=; continue ;;
      esac
      case "$argument" in
        -p|--project-name) previous=$argument ;;
        --project-name=*) project=${argument#*=} ;;
      esac
    done
    # Docker's name filter matches substrings; compare every name exactly.
    if ! volumes=$(docker volume ls --format '{{.Name}}' 2>/dev/null); then
      echo "scripts/dc.sh: Cannot inspect Docker volumes; refusing to start storage without checking for a legacy MinIO volume." >&2
      exit 2
    fi
    has_volume() {
      printf '%s\n' "$volumes" | grep -Fxq "$1"
    }
    legacy=
    legacy_sources=
    for name in "${project}_minio-data" "${project}_minio_data"; do
      if has_volume "$name"; then
        legacy="$legacy $name"
        [ -z "$legacy_sources" ] || legacy_sources="$legacy_sources,"
        legacy_sources="$legacy_sources$name"
      fi
    done
    target_volume="${project}_seaweedfs_data"
    if [ -n "$legacy" ]; then
      attestation_file="$ROOT/.secrets/s3-cutover-attestation.txt"
      expected_attestation=$(printf 'schema_version=1\nproject_name=%s\nlegacy_source_volumes=%s\ntarget_volume=%s\nverified=VERIFIED_S3_CUTOVER' \
        "$project" "$legacy_sources" "$target_volume")
      actual_attestation=
      if [ -f "$attestation_file" ]; then
        actual_attestation=$(tr -d '\r' < "$attestation_file") || actual_attestation=
      fi
      if ! has_volume "$target_volume" || [ "$actual_attestation" != "$expected_attestation" ]; then
        echo "scripts/dc.sh: Legacy MinIO volume${legacy} requires existing target '$target_volume' and exact verified attestation .secrets/s3-cutover-attestation.txt. Follow docs/runbooks/s3-seaweedfs-cutover.md first." >&2
        exit 2
      fi
    fi
fi

docker compose -f docker-compose.full.yml --env-file "$ENV_FILE" "$@"
