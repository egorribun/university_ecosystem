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

The script requires pg_dump and pg_restore on PATH. Their diagnostics are
suppressed so a driver error cannot print connection material. S3 credentials
are never added to subprocess arguments.

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
with pg_restore --list, then creates the new database and restores without
owner/privilege changes. It never drops databases or replaces existing data.
If restore fails after database creation, the partial target is left for
operator inspection; use a new target name after resolving it.

Replace the example object key with the exact manifest key printed by the
backup command:

~~~powershell
uv run python scripts/backup_db.py restore --manifest-key database/university-20260930T123000Z-00000000000000000000000000000000.dump.manifest.json --target-database restore_university_20260930
~~~

## Scope and limits

This is a database-only artifact. It does not back up or restore user objects
from S3 and does not establish a coordinated recovery point between PostgreSQL
rows and object storage. The manifest revision is the Alembic database revision,
not the application source commit. Compare the revision before and after the
dump; a change aborts publication.

The Helm CronJob still has its separate direct pg_dump/rclone implementation
and is not yet wired to this manifest/restore CLI. No restore has been run
against a deployed Docker/kind stack, and this implementation does not certify
RPO ≤24 hours or RTO ≤30 minutes. Those require an isolated end-to-end database
and object-storage restore, freshness monitoring, and measured recovery evidence.
