# S3 cutover to SeaweedFS (Core/full Compose and staging)

Status: **prepared, not executed**. The normal Core/full Compose files still use
MinIO. The optional `docker-compose.seaweedfs-cutover.yml` overlay is a switch
for a *verified* migration only. It cannot read MinIO's on-disk format, mounts
the distinct `university_ecosystem_seaweedfs_data` volume, and retains the old
MinIO volume. Never use `docker compose down -v` during this procedure.

## Stop conditions

Do not switch if any of these is missing:

- A reachable, authenticated **old S3 API** and a restorable backup of the old
  volume. A cached image or a small volume size does not prove there are no
  objects. If the old API cannot be started, stop and preserve the volume.
- An empty, independent SeaweedFS target volume, with its S3 API available to
  the migration operator. Do not mount `minio_data` or `minio-data` at `/data`
  in SeaweedFS.
- Writes paused for backend uploads, file processor, background jobs and any
  other S3 writers. Repeat inventory after the pause; any drift blocks cutover.
- An object copy preserving exact keys, bytes, Content-Type, Cache-Control and
  relevant user metadata. `scripts/s3_cutover_preflight.py verify` must pass.
  Versioned buckets require a separate version-aware procedure and are rejected.
- A browser-reachable public media delivery path for `avatars`, `covers`,
  `news_images`, `story_covers`, and `tmp/event_images`. The intended route is
  the credentialed backend image proxy at `/api/v1/img/<key>`; verify its
  prefix allowlist and returned URLs end to end. SeaweedFS's default private
  bucket returns 403 for unsigned GET; this overlay does **not** make the
  bucket public. Until that route and historical URL compatibility are
  verified, the Compose backend must remain on static storage and staging
  must not switch its S3 endpoint.
- Legacy `/storage/uploads/<public-prefix>/...` URLs, if any, must remain
  read-only and scoped to the exact bucket and reviewed public prefixes.
  Caddy rejects PUT/DELETE and other bucket names, but the destination bucket
  remains private; verify historical URLs through a tested redirect or migrate
  references before switching, rather than opening bucket-wide anonymous GET.
- Private `chat_uploads`, `event_files`, and `quarantine` objects denied by
  direct unsigned GET. Chat/event downloads must use their authorized backend
  APIs with `private, no-store` responses. Never enable bucket-wide public ACL.
- A rollback window during which the old volume and old service configuration
  remain intact. New writes after cutover must be inventoried and reconciled
  before any rollback; simply changing images back would lose those writes.

## Read-only inventory and verification

Supply credentials through a protected environment or secret manager, not CLI
arguments, shell history, Compose files, or this runbook. The operator must set
`S3_CUTOVER_BUCKET=uploads` and `S3_SOURCE_ENDPOINT`,
`S3_SOURCE_ACCESS_KEY`, `S3_SOURCE_SECRET_KEY`. Verification also needs the
corresponding `S3_TARGET_*` variables. Endpoints are bare HTTPS origins by
default; `--allow-http-local` is limited to loopback and the local Compose DNS
names `minio` and `seaweedfs-target`.
The preflight rejects bucket names other than the deployed `uploads` bucket,
unresolved endpoints, and endpoints whose DNS addresses overlap, even when
their ports differ. Also independently attest that source and target use different services
and volumes: a proxy or DNS rebind can defeat hostname checks.

```text
uv run python scripts/s3_cutover_preflight.py inventory
uv run python scripts/s3_cutover_preflight.py verify
```

The tool reads all current objects, hashes bytes, checks key count, size,
Content-Type and Cache-Control, and never calls Put/Delete. It emits only counts
and aggregate hashes, not keys or credentials. Run inventory on the old API
before copying, copy with a vetted S3-to-S3 tool, freeze writers, copy the final
delta, then run `verify` against both endpoints. Keep a separate backup and
restore-test it; this tool is not a backup or copy engine. If object tags, ACLs,
retention, legal holds, server-side encryption, or historical versions are in
use, document and verify them separately before proceeding.

## Compose activation (only after every stop condition passes)

1. Inspect `docker compose config --no-interpolate` for the actual Core or full
   stack plus the cutover overlay **last**. Confirm `minio` mounts only
   `seaweedfs_data`, port 9001 is absent, and old volumes remain untouched.
2. Set `S3_CUTOVER_ACK` only for this controlled deployment, then bring up the
   selected stack with the overlay last. The overlay keeps the `minio:9000`
   service DNS name for existing clients and replaces the `minio-init` client
   with a readiness check. Do not combine it with the infra port-publishing
   override after the cutover overlay.
3. Prove Python `aioboto3` and Go `minio-go` Put/Head/Get/Delete, MIME and
   Cache-Control, presigned GET, health probes, private 403, authorized private
   download, public media, and backup upload/restore on the actual endpoint.
4. Monitor errors and object counts. Keep the old volume and backup unchanged
   until the rollback window closes and a separate retention decision is made.

## Staging/Helm

Helm deploys **external** object storage and does not run this Compose overlay.
Set a TLS SeaweedFS S3 endpoint separately for backend and file processor,
inject distinct non-default credentials through the existing Secret mechanism,
and update egress policy for the actual service labels/port. The backend's
`storageS3BaseURL` must be a deliberate browser-reachable public delivery URL
such as the validated `/api/v1/img` route, not the internal S3 API. Preserve
historical persisted URL host/key semantics
or migrate database references with a verified reversible procedure. The Helm
Ingress currently has no storage backend route. Do not substitute a placeholder
SeaweedFS endpoint in `values-staging.yaml` and declare staging migrated.

Release evidence must include current-SHA CI storage integration tests,
staging upload/read/delete and private-access checks, a verified object inventory,
and backup restore. Without access to the old API and external staging, this
repository change is **preparation only**, not a production data cutover.
