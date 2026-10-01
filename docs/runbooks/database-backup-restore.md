# PostgreSQL backup artifact CLI

This runbook covers the versioned logical backup artifact created by
scripts/backup_db.py. It writes a PostgreSQL custom-format dump and a
versioned JSON manifest to the configured S3-compatible endpoint. The manifest
contains the source database name, current Alembic revision(s), UTC timestamp,
dump format, byte size, object key, and SHA-256. It deliberately omits the
database host, username, password, and S3 credentials.

## Environment

Before running the commands, provide these values through the process
environment or the existing secret provider. Never put a connection URL,
password, or access key in command arguments or logs.

- DATABASE_URL: PostgreSQL source connection URL for backup.
- BACKUP_S3_ENDPOINT_URL and BACKUP_S3_BUCKET: required S3 endpoint and bucket.
- S3 endpoints must use HTTPS. For an isolated local/development endpoint only,
  set `BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV=true` to opt in to plain HTTP. With
  that opt-in, the endpoint host must be a loopback address, an RFC1918 IPv4 or
  IPv6 ULA address, or one of the local endpoint names used by the repository:
  `localhost`, `minio`, or `seaweedfs`. Public and link-local addresses (including metadata
  endpoints) and arbitrary DNS names are rejected. Never use HTTP on an
  untrusted network.
- BACKUP_S3_PREFIX: optional key prefix, default database.
- S3 credentials: the standard aioboto3/AWS credential provider chain.
- BACKUP_RESTORE_ADMIN_DATABASE_URL: separate administrative PostgreSQL URL
  used only for restore; it must have permission to create a database.

The script requires pg_dump, pg_restore, and createdb on PATH. Client utility
diagnostics are suppressed so a driver error cannot print connection material.
Database credentials are passed through the PostgreSQL client environment;
database names are separate validated arguments. S3 credentials are never
added to subprocess arguments.

## Create a backup

With the environment already configured:

~~~powershell
uv run python scripts/backup_db.py backup
~~~

The command creates a unique .dump object, reads it back to verify its size
and SHA-256, then uploads and reads back the matching manifest. It prints the
manifest object key only after both checks succeed. The default invocation
without a subcommand is equivalent to backup.

## Restore into a new database

Choose a disposable or otherwise isolated PostgreSQL target and configure
BACKUP_RESTORE_ADMIN_DATABASE_URL for that target. Provide a new database
name beginning with restore_; the script refuses a name matching the source
database and refuses to use an existing database.

Restore validates the manifest schema, downloads the referenced dump to a
temporary file, verifies its byte count and SHA-256, checks the custom archive
with pg_restore --list, then creates the new database with createdb and
restores without owner/privilege changes. It never drops databases or replaces
existing data.
If restore fails after database creation, the partial target is left for
operator inspection; use a new target name after resolving it.

Replace the example object key with the exact manifest key printed by the
backup command:

~~~powershell
uv run python scripts/backup_db.py restore --manifest-key database/university-20260930T123000Z-00000000000000000000000000000000.dump.manifest.json --target-database restore_university_20260930
~~~

## Create a coordinated database and object snapshot

The `snapshot` command creates schema-v2 paired snapshots. Before invoking it,
pause all application writes to PostgreSQL and the configured application S3
bucket, and keep them paused until the command reports success. Then run:

~~~powershell
uv run python scripts/backup_db.py snapshot --confirm-source-quiesced
~~~

The required flag is an operator attestation; the script cannot pause or prove
that external writers have stopped. It records the confirmation timestamp and
`operator_quiesced` consistency mode in the v2 manifest. It also compares the
database name and Alembic revision before and after the dump. The application
object source must be configured with `STORAGE_BACKEND=s3` or `minio` and the
existing `StorageSettings` fields `STORAGE_S3_BUCKET`,
`STORAGE_S3_ENDPOINT_URL`, `STORAGE_S3_REGION`,
`STORAGE_S3_ACCESS_KEY_ID`, and `STORAGE_S3_SECRET_ACCESS_KEY`. Empty endpoint
uses the SDK's configured AWS endpoint; empty region defaults to `us-east-1`.
Credentials can come from the configured environment, application `.env` or
the AWS SDK credential provider chain. Never put credentials in arguments.

The source object bucket and `BACKUP_S3_BUCKET` must differ. The snapshot
inventory includes every current object returned by paginated `ListObjectsV2`;
each read is pinned to the listed ETag and records a source VersionId when the
endpoint returns one. Endpoints must expose complete pagination markers and
object ETags. Unversioned sources are supported only while the operator keeps
the source quiesced; their bytes and ETag are recorded. Archived database and
object artifacts use run-scoped keys, conditional create-only writes, and
read-back size/SHA-256 checks. The paired manifest, which links the database
dump and every object copy, is written last as the commit marker. The current
limits are 100,000 source objects and a 64 MiB manifest; larger inventories
fail closed and are never truncated or published.

If a process stops before publishing the manifest, the run can leave
unreferenced immutable objects under its `snapshots/<snapshot-id>/` prefix.
The script does not delete them. A failure while publishing or reading back
the final manifest has an uncertain outcome: inspect that run's manifest and
artifacts before retrying. Use storage lifecycle policy or a separately
reviewed cleanup procedure; do not delete by broad prefix without proving run
ownership.

## Restore a paired snapshot into isolated targets

Choose an object bucket distinct from both the source object bucket and
`BACKUP_S3_BUCKET`. The restore target is a required bucket and prefix pair;
the prefix may be empty when restoring keys at the bucket root. The selected
prefix must have no current objects, versions, delete markers, or incomplete
multipart uploads. Configure
`BACKUP_RESTORE_ADMIN_DATABASE_URL` to a PostgreSQL administrative database,
choose a nonexistent database named `restore_<name>`, and run:

~~~powershell
uv run python scripts/backup_db.py restore-snapshot --manifest-key database/snapshots/<snapshot-id>/database.manifest.json --target-database restore_university_demo --objects-target-bucket university-restore-20261001 --objects-target-prefix restore-20261001
~~~

Before writes, restore validates the v2 manifest, downloads and verifies the
database dump and every unique object copy, checks that the database target
does not exist, and checks that the selected target prefix has no current
objects, versions, delete markers, or incomplete multipart uploads. To restore
at the bucket root, pass `--objects-target-prefix ""` explicitly. The target
S3 endpoint must support `ListObjectVersions`, `ListMultipartUploads`, pinned
`GetObject` reads, and `If-None-Match: *` for `PutObject` and
`CompleteMultipartUpload`. Unsupported or incomplete preflight/conditional
operations fail closed. Conditional creates prevent a concurrent writer from
replacing an object. Object bytes are restored under
`<target-prefix>/<original-key>`, and listed HTTP metadata is preserved.

The restore is isolated, not a distributed transaction. PostgreSQL and S3 do
not share an atomic commit. If the command stops after the database restore or
some object writes, it leaves the newly created database and any target
objects untouched for inspection; it never removes source data or performs
best-effort cleanup. Keep the target database and object prefix disconnected
from the application until the command succeeds and an operator validates the
result. After a partial restore, inspect the isolated targets and use a new
database name and empty object prefix for another attempt. The script never
overwrites a database or object.

## Scope and limits

The original `backup` and `restore` commands remain schema-v1 database-only
operations for compatibility. Use `snapshot` and `restore-snapshot` when a
coordinated database/object recovery point is required. The v2 manifest's
revision is the Alembic database revision, not the application source commit.
Quiescence is attested by the operator and cannot be independently established
by the CLI.

The Helm CronJob still has its separate direct pg_dump/rclone implementation
and is not yet wired to this manifest/restore CLI. Only mocked S3/database
checks have been run for this code path. No restore has been run against a
deployed Docker/kind stack, and this implementation does not certify RPO ≤24
hours or RTO ≤30 minutes. Those require an isolated end-to-end restore,
freshness monitoring, concurrent-write controls, and measured recovery evidence.
