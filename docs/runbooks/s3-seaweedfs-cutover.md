# Migrating a legacy MinIO volume to SeaweedFS

Every Compose stack runs SeaweedFS as its S3 storage
([ADR-042](../adr/ADR-042-seaweedfs-default-object-storage.md)). The service
keeps the `minio` name (`minio:9000`) and stores its data in the Docker volume
`<project>_seaweedfs_data` (`university_ecosystem_seaweedfs_data` by default).
Both base Compose files declare `name: university_ecosystem`; an explicit
`COMPOSE_PROJECT_NAME` or wrapper `-p` selects another project-scoped name.
SeaweedFS cannot read MinIO's on-disk format, and the Compose files no longer
declare the legacy MinIO volumes, so a volume created by an older checkout is
never mounted, changed or deleted by Compose:

| Created by | Legacy volume |
| --- | --- |
| `start-docker.ps1` / `docker-compose.full.yml` | `<project>_minio-data` |
| `docker-compose.yml` | `<project>_minio_data` |

`<project>` is the effective Compose project: `-p` first, then
`COMPOSE_PROJECT_NAME`, then the `.env.docker` value, then the Compose model's
default `university_ecosystem`.

## The launcher guard

`start-docker.ps1`, `scripts/dc.ps1` and `scripts/dc.sh` refuse to start when
any legacy MinIO volume matching the current project exists unless the exact
`<project>_seaweedfs_data` target exists and the ignored local file
`.secrets/s3-cutover-attestation.txt` matches the project, **all** matching
legacy source volumes, target volume, and `verified=VERIFIED_S3_CUTOVER` marker.
A target volume's existence by itself proves nothing about its contents. If
Docker cannot list volumes, the start is refused as well.

The attestation is an explicit operator record, not automated proof. Write it
only after the inventory/empty-bucket check or object copy and successful
`verify` procedure below, and keep it in the checkout so all three launchers
read the same durable evidence. Direct `docker compose` commands bypass the
guard; do not use them for the first start.

Never run `docker compose down -v`, `docker volume rm` or `docker volume prune`
to get past the guard. Keep the legacy volume and its backup until the
retention decision at the end of this runbook.

## 1. Freeze and back up

1. Stop the stack: `.\start-docker.ps1 -Down` (never `-v`).
2. Confirm which legacy volume exists: `docker volume ls`.
3. Back up the volume read-only and restore-test the archive into a scratch
   copy. The legacy server later runs on the copy, so the original volume is
   never mounted writable:

   ```pwsh
   $legacy = "university_ecosystem_minio-data"   # from step 2
   $alpine = "alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc"
   $backup = Join-Path $HOME "s3-migration"      # outside the repository
   New-Item -ItemType Directory -Force $backup | Out-Null
   docker run --rm -v "${legacy}:/data:ro" -v "${backup}:/backup" $alpine `
     tar -C /data -czf /backup/minio-data.tgz .
   docker volume create s3-legacy-copy
   docker run --rm -v s3-legacy-copy:/data -v "${backup}:/backup:ro" $alpine `
     tar -C /data -xzf /backup/minio-data.tgz
   ```

   The archive holds user files; never copy it into the repository.

## 2. Start the legacy S3 API

MinIO no longer publishes images, so the legacy server comes from one of:

- a **locally cached image**, if `docker image inspect
  quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`
  succeeds; or
- a **build from the pinned source tag** `RELEASE.2025-09-07T16-13-09Z` of
  `github.com/minio/minio` (for example `CGO_ENABLED=0 go build -trimpath -o
  minio .` in a checkout of that tag, copied into a minimal image and tagged
  `local/minio-legacy:RELEASE.2025-09-07T16-13-09Z`). MinIO is AGPL-3.0: use
  this image only for the migration, never push it or reference it from a
  Compose file, and delete it when the migration is closed.

Run it as `minio` on an internal migration network, on the copy, with the
credentials from `.env.docker` (supply them through the environment, not the
command line):

```pwsh
docker network create --internal s3-migration
$env:MINIO_ROOT_USER = "<MINIO_ROOT_USER from .env.docker>"
$env:MINIO_ROOT_PASSWORD = "<MINIO_ROOT_PASSWORD from .env.docker>"
docker run -d --name s3-legacy --network s3-migration --network-alias minio `
  -e MINIO_ROOT_USER -e MINIO_ROOT_PASSWORD -v s3-legacy-copy:/data `
  <legacy image> server /data
```

## 3. Inventory the legacy bucket

`scripts/s3_cutover_preflight.py` reads every current object, hashes bytes and
compares Content-Type, Cache-Control and user metadata. It never writes or
deletes, and prints only counts and aggregate hashes. Run it on the migration
network from an image that has the backend's Python dependencies, such as the
stack's backend image (`docker compose -f docker-compose.full.yml --env-file
.env.docker images backend`):

```pwsh
$env:S3_SOURCE_ACCESS_KEY = $env:MINIO_ROOT_USER
$env:S3_SOURCE_SECRET_KEY = $env:MINIO_ROOT_PASSWORD
docker run --rm --network s3-migration -v "${PWD}/scripts:/migration:ro" `
  -e S3_CUTOVER_BUCKET=uploads -e S3_SOURCE_ENDPOINT=http://minio:9000 `
  -e S3_SOURCE_ACCESS_KEY -e S3_SOURCE_SECRET_KEY `
  <backend image> python /migration/s3_cutover_preflight.py inventory --allow-http-local
```

A versioned bucket is rejected and needs a separate, version-aware procedure.
If object tags, ACLs, retention, legal holds or server-side encryption are in
use, document and verify them separately. If the legacy API cannot be started
at all, stop here and keep the volume: a small volume size does not prove the
bucket is empty.

## Record the verified migration

Run this helper **only after** `inventory` reported an empty bucket or the
source-to-target `verify` command printed `object inventory matches` for
every legacy source. If both legacy naming variants exist, they are separate
data sources: inventory and reconcile both before attesting. One successful
single-source verify does not cover the other volume; if their contents cannot
be safely reconciled, stop and preserve both. The helper binds the local
record to the current project, every matching legacy source volume, and that
project's exact target volume. For a wrapper invocation with `-p`, pass that
same project name explicitly; otherwise the function resolves the
environment, `.env.docker`, and default name in the same order as the launchers.

```pwsh
function Write-S3CutoverAttestation {
  param([Parameter(Mandatory)][string]$Project)

  $names = @("${Project}_minio-data", "${Project}_minio_data")
  $existing = @(docker volume ls --format '{{.Name}}')
  $sources = @($names | Where-Object { $existing -ccontains $_ })
  if ($sources.Count -eq 0) { throw "No matching legacy source volume for '$Project'." }
  $target = "${Project}_seaweedfs_data"
  if ($existing -cnotcontains $target) { throw "Create and verify target volume '$target' first." }

  $lines = @(
    'schema_version=1',
    "project_name=$Project",
    "legacy_source_volumes=$($sources -join ',')",
    "target_volume=$target",
    'verified=VERIFIED_S3_CUTOVER'
  )
  $directory = Join-Path (Get-Location) '.secrets'
  New-Item -ItemType Directory -Force -Path $directory | Out-Null
  $path = Join-Path $directory 's3-cutover-attestation.txt'
  Set-Content -LiteralPath $path -Value (($lines -join "`n") + "`n") `
    -NoNewline -Encoding utf8NoBOM
  Get-Content -LiteralPath $path
}

$project = $env:COMPOSE_PROJECT_NAME
if ([string]::IsNullOrWhiteSpace($project)) {
  $entry = Get-Content .env.docker | Where-Object { $_ -match '^\s*COMPOSE_PROJECT_NAME\s*=' } | Select-Object -Last 1
  if ($entry) { $project = ($entry -split '=', 2)[1].Trim().Trim('"', "'") }
}
if ([string]::IsNullOrWhiteSpace($project)) { $project = 'university_ecosystem' }
# Keep start-docker.ps1, Compose, and the attestation on the same identity.
$env:COMPOSE_PROJECT_NAME = $project
# If the supported wrapper uses -p, pass this same explicit value there too.
```

## 4a. Empty legacy bucket

If inventory reports `source count=0` for **every** matching legacy bucket,
nothing needs copying. Stop the legacy server (step 6), create the project's
empty target, and write the attestation only after confirming all counts:

```pwsh
$target = "${project}_seaweedfs_data"
docker volume create $target
Write-S3CutoverAttestation -Project $project
.\start-docker.ps1          # add -Core, -Build or -Rebuild as usual
```

## 4b. Legacy bucket with objects

Copy into the stack's own SeaweedFS volume while the stack is stopped, so no
writer can change either side. Start a temporary target with the same image
and command as the `minio` service in `docker-compose.full.yml`:

```pwsh
$target = "${project}_seaweedfs_data"
docker volume create $target
$seaweed = "ghcr.io/chrislusf/seaweedfs:4.47@sha256:ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882"
docker run -d --name s3-target --network s3-migration --network-alias seaweedfs-target `
  -e AWS_ACCESS_KEY_ID=$env:MINIO_ROOT_USER -e AWS_SECRET_ACCESS_KEY=$env:MINIO_ROOT_PASSWORD `
  -e S3_BUCKET=uploads -v "${target}:/data" `
  $seaweed mini -dir=/data -s3.port=9000
```

Copy with a vetted S3-to-S3 tool that keeps exact keys, bytes, Content-Type,
Cache-Control and user metadata, for example the pinned rclone image the Helm
backup uses (`backup.s3ClientImage`) with `rclone copy --metadata --checksum`
and both remotes defined through `RCLONE_CONFIG_<NAME>_*` environment
variables (`provider=Minio` for the source, `provider=SeaweedFS` for the
target). Then verify:

```pwsh
$env:S3_TARGET_ACCESS_KEY = $env:MINIO_ROOT_USER
$env:S3_TARGET_SECRET_KEY = $env:MINIO_ROOT_PASSWORD
docker run --rm --network s3-migration -v "${PWD}/scripts:/migration:ro" `
  -e S3_CUTOVER_BUCKET=uploads `
  -e S3_SOURCE_ENDPOINT=http://minio:9000 -e S3_SOURCE_ACCESS_KEY -e S3_SOURCE_SECRET_KEY `
  -e S3_TARGET_ENDPOINT=http://seaweedfs-target:9000 -e S3_TARGET_ACCESS_KEY -e S3_TARGET_SECRET_KEY `
  <backend image> python /migration/s3_cutover_preflight.py verify --allow-http-local
```

`verify` must print `object inventory matches`. Any difference blocks the
start: fix the copy and verify again. The preflight also refuses source and
target endpoints that resolve to the same address. Independently confirm that
`s3-legacy` and `s3-target` use different volumes.

After `verify` prints `object inventory matches`, stop and remove the
temporary target (`docker rm -f s3-target`) and write the local attestation:

```pwsh
Write-S3CutoverAttestation -Project $project
.\start-docker.ps1          # add -Core, -Build or -Rebuild as usual
```

The target volume and the matching attestation are both required. Keep the
attestation with this checkout for subsequent launcher and wrapper starts.

## 5. Check the running stack

After the first start, prove on the real endpoint: Python `aioboto3` and Go
`minio-go` Put/Head/Get/Delete, MIME and Cache-Control, presigned GET, private
objects (`chat_uploads`, `event_files`, `quarantine`) denied on unsigned GET,
authorized downloads through the backend APIs, and public media under the
reviewed prefixes (`avatars`, `covers`, `news_images`, `story_covers`,
`tmp/event_images`). SeaweedFS buckets are private: unsigned GET through
Caddy's `/storage/*` route returns 403, so public media must be served through
the credentialed backend image route `/api/v1/img/<key>`. Reconcile historical
`/storage/uploads/...` or off-origin references with a tested migration;
never add an implicit URL-to-key fallback or make the bucket public.

## 6. Clean up and retention

Remove the legacy server, the migration network and the scratch copy:
`docker rm -f s3-legacy`, `docker network rm s3-migration`, `docker volume rm
s3-legacy-copy`, and the locally built legacy image, if any. Keep the original
legacy volume and the backup archive until a separate retention decision is
recorded; new writes after the start would have to be reconciled before any
return to the legacy data.

## Staging/Helm

Helm deploys **external** object storage and does not run Compose. Set a TLS
S3 endpoint separately for backend and file processor, inject distinct
non-default credentials through the existing Secret mechanism, and update the
egress policy for the actual service labels and port. The backend's
`storageS3BaseURL` must be a deliberate browser-reachable delivery URL such as
the validated `/api/v1/img` route, not the internal S3 API. Moving existing
staging objects follows the same inventory, copy and `verify` gates against
the two HTTPS endpoints (without `--allow-http-local`). Do not substitute a
placeholder endpoint in `values-staging.yaml` and declare staging migrated.
Release evidence must include current-SHA CI storage integration tests,
staging upload/read/delete and private-access checks, a verified object
inventory, and a backup restore.
