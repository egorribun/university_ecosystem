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
# unavailable here; use the reviewed cutover launcher/runbook for those flows.
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

# The base file still defines legacy MinIO. Never let an `up` (including one
# scoped to another service) silently reattach that old volume after cutover.
# Keep read-only inspection and shutdown commands available for recovery.
guard_required=1
compose_command=
compose_command_index=0
expect_project=0
argument_index=0
for argument do
  argument_index=$((argument_index + 1))
  case "$argument" in
    -f*|-p?*|--file|--file=*|--project-directory|--project-directory=*|--env-file|--env-file=*)
      echo "scripts/dc.sh: Compose topology overrides are not supported; use the reviewed storage launcher." >&2
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
      echo "scripts/dc.sh: Compose topology overrides are not supported; use the reviewed storage launcher." >&2
      exit 2 ;;
    -f*)
      case "$compose_command" in
        logs|exec) ;;
        *)
          echo "scripts/dc.sh: Compose topology overrides are not supported; use the reviewed storage launcher." >&2
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
        --rmi|--rmi=*)
          echo "scripts/dc.sh: Refusing Compose down --rmi; preserve the cached legacy S3 image until migration and rollback are verified." >&2
          exit 2 ;;
      esac
    done
    ;;
esac
# A persistent directory lock coordinates legacy Compose mutations with the
# migration-aware launcher. An existing/stale lock is never removed for us.
case "$compose_command" in
  ps|logs|config|images|top|ls|version|events|port) ;;
  *)
    lock_path="$ROOT/.secrets/s3-storage-compose.lock"
    mkdir -p "$ROOT/.secrets"
    if ! mkdir "$lock_path" 2>/dev/null; then
      echo "scripts/dc.sh: S3 storage Compose lock is held; inspect it before retrying." >&2
      exit 2
    fi
    cleanup_storage_lock() {
      status=$?
      trap - EXIT INT TERM
      if ! rmdir "$lock_path"; then
        echo "scripts/dc.sh: Cannot release owned S3 storage Compose lock; manual inspection required." >&2
        [ "$status" -eq 0 ] && status=2
      fi
      exit "$status"
    }
    trap cleanup_storage_lock EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    ;;
esac
if [ "$guard_required" -eq 1 ]; then
    marker="$ROOT/.secrets/s3-seaweedfs-cutover-initiated"
    volume_name=university_ecosystem_seaweedfs_data
    if [ -e "$marker" ]; then
      echo "scripts/dc.sh: SeaweedFS cutover marker exists; refusing a possible MinIO rollback. Use start-docker.ps1 -SeaweedFS after runbook verification." >&2
      exit 2
    fi

    project=${COMPOSE_PROJECT_NAME:-}
    if [ -z "$project" ]; then
      while IFS='=' read -r key value; do
        if [ "$key" = COMPOSE_PROJECT_NAME ]; then
          project=$value
        fi
      done < "$ENV_FILE"
      # Compose accepts quoted env-file values; remove one matching pair.
      case "$project" in
        \"*\") project=${project#\"}; project=${project%\"} ;;
        \'*\') project=${project#\'}; project=${project%\'} ;;
      esac
    fi
    if [ -z "$project" ]; then
      project=$(basename "$ROOT" | tr '[:upper:]' '[:lower:]')
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
    if ! storage_images=$(docker ps -a \
      --filter "label=com.docker.compose.project=$project" \
      --filter "label=com.docker.compose.service=minio" \
      --format '{{.Image}}' 2>/dev/null); then
      echo "scripts/dc.sh: Cannot inspect Compose storage containers; refusing a possible MinIO rollback." >&2
      exit 2
    fi
    if printf '%s\n' "$storage_images" | grep -qi seaweedfs; then
      echo "scripts/dc.sh: SeaweedFS storage container exists; refusing a possible MinIO rollback." >&2
      exit 2
    fi
    if ! cutover_volumes=$(docker volume ls \
      --filter "name=^$volume_name$" --format '{{.Name}}' 2>/dev/null); then
      echo "scripts/dc.sh: Cannot inspect S3 storage volumes; refusing a possible MinIO rollback." >&2
      exit 2
    fi
    if printf '%s\n' "$cutover_volumes" | grep -Fxq "$volume_name"; then
      echo "scripts/dc.sh: SeaweedFS storage volume exists; refusing a possible MinIO rollback." >&2
      exit 2
    fi
fi

docker compose -f docker-compose.full.yml --env-file "$ENV_FILE" "$@"
