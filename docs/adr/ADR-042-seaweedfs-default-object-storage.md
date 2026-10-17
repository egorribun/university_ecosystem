# ADR-042: SeaweedFS as the Default Object Storage

## Status

Accepted

## Date

2026-09-29

## Context

The Compose stacks (`docker-compose.yml`, `docker-compose.full.yml`) ran MinIO
for S3 storage and its `mc` client to create the `uploads` bucket. In
September 2026 MinIO stopped publishing images: pulls of `quay.io/minio/minio`
and `quay.io/minio/mc` return 401, and the Docker Hub repository was already
archived. A fresh machine could no longer start the stack, so
`start-docker.ps1` was broken for new installs.

SeaweedFS was already audited and in use:

- the disposable test sandbox, the CI chaos fixture, the nightly S3 cell and
  the file-processor Testcontainers suite run `ghcr.io/chrislusf/seaweedfs:4.47`
  pinned by digest;
- the owned live stand (`docker-compose.live.yml`) replaced MinIO with it;
- an opt-in `docker-compose.seaweedfs-cutover.yml` overlay, a `-SeaweedFS`
  launcher switch and a runbook prepared a verified switch for existing
  installs, guarded by a cutover marker, anti-rollback checks and a Compose
  lock.

SeaweedFS cannot read MinIO's on-disk format. A machine that ran the old
stack keeps its objects in a legacy volume (`<project>_minio-data` from the
full stack, `<project>_minio_data` from the base file) that only a MinIO
server can serve.

## Decision

SeaweedFS 4.47 (`weed mini`, pinned by digest) is the S3 storage of every
Compose path. No runnable Compose file references a MinIO image.

- The service keeps the `minio` name, so backend, Caddy and file-processor
  keep using `minio:9000` and the `MINIO_*` variables. The root credentials
  map to `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`; `S3_BUCKET=uploads`
  makes SeaweedFS create the bucket. There is no console and no published
  port; `docker-compose.infra.yml` publishes only the S3 API on loopback.
- `minio-init` keeps its name for dependency ordering and only waits for the
  S3 API (`/status`) with the same image; `mc` is gone.
- Data lives in project-scoped `seaweedfs_data`; both base Compose models
  declare `name: university_ecosystem` to retain the default
  `university_ecosystem_seaweedfs_data` name while custom projects remain
  isolated. The live stand inherits that project-scoped behavior.
- The legacy MinIO volumes are no longer declared. Compose never mounts or
  deletes them.
- `start-docker.ps1`, `scripts/dc.ps1` and `scripts/dc.sh` refuse to start
  storage when a legacy volume of the Compose project exists unless both the
  exact project target volume and an ignored local attestation match the
  project, all matching source volumes, target, and verified marker. A target
  volume's existence alone is insufficient, and failed volume inspection
  refuses. The migration follows `docs/runbooks/s3-seaweedfs-cutover.md`.
- The overlay, the `-SeaweedFS` switch, the ephemeral `S3_CUTOVER_ACK` bypass,
  anti-rollback checks, storage Compose lock and wrappers' `down --rmi`
  refusal are removed: without a MinIO path there is nothing to roll back to,
  and no Compose model can remove the cached MinIO image.
- Prometheus no longer scrapes the MinIO metrics job, and the launcher no
  longer waits for it.

## Consequences

- A fresh machine starts the full and Core stacks without MinIO images.
- An existing install with a legacy volume stops at the guard until its
  objects are migrated (or the bucket is confirmed empty with
  `scripts/s3_cutover_preflight.py inventory`) and the operator records the
  project/source/target-bound attestation. The legacy server for that
  migration must come from a locally cached image or a build of the pinned
  MinIO source tag (AGPL-3.0), used only for the migration.
- Direct `docker compose ... up` bypasses the guard; the launcher and wrappers
  are the supported entry points, as before.
- The live stand inherits the full stack's project-scoped `seaweedfs_data`
  volume. Its unique run-owned project is `ue-live-<16 hex>`, so its volume is
  `<run-project>_seaweedfs_data`; the former fixed `ue-live` project name is
  not the current owner identity.
- Storage has no metrics in Prometheus. SeaweedFS metrics are an open
  follow-up: `weed mini` with `-metricsPort`/`-s3.metricsPort` stopped
  serving S3 on 9000 in a first attempt and needs a separate check.
- Helm deploys external S3 storage and is unaffected, except that the backup
  CronJob uploads with rclone instead of `mc` since `ee90ce97e`.
- Renovate keeps the SeaweedFS image on the manual-review schedule that
  previously covered the MinIO images.

## Alternatives considered

- **Keep MinIO from a mirror or a source build.** Rejected: no maintained
  images, AGPL-3.0 builds would have to be owned by this repository, and every
  fresh install would depend on them.
- **Keep the opt-in overlay and make SeaweedFS the exception.** Rejected: the
  default path cannot start on a fresh machine.
- **Garage.** Not pursued: SeaweedFS was already pinned, audited and exercised
  by CI, the sandbox and the live stand.

## References

- [S3 migration runbook](../runbooks/s3-seaweedfs-cutover.md)
- `tests/test_s3_cutover_compose_contract.py`,
  `tests/test_start_docker_cutover.py`,
  `tests/test_compose_storage_wrapper_guard.py`
