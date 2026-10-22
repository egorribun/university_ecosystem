# Rejected-upload quarantine

Rejected payloads use the private `quarantine/` storage namespace. A durable
PostgreSQL ledger reserves bytes before each write and serializes admission
for workers sharing a storage scope. Exhausted quota or unsafe storage inventory
prevents persistence; the upload still receives its original rejection.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `STORAGE_QUARANTINE_QUOTA_BYTES` | `1073741824` | Maximum charged payload bytes per storage scope |
| `STORAGE_QUARANTINE_RETENTION_DAYS` | `7` | Retention after an acknowledged stored write |
| `STORAGE_QUARANTINE_SWEEP_INTERVAL_SECONDS` | `300` | API-process cleanup interval |
| `STORAGE_QUARANTINE_INVENTORY_PAGE_SIZE` | `100` | Bounded bootstrap page size |
| `STORAGE_QUARANTINE_SCOPE_ID` | Empty | Shared scope override for storage aliases |

Use the same scope override for all writers addressing one physical store
through different filesystem paths or S3 endpoint aliases. The override is
hashed before persistence. Inventory must complete before admitting new writes;
malformed keys, missing protocol fields, or unsafe entries keep admission closed.

## Capacity and retention

`pending`, `stored`, and `deleting` rows all consume quota. Only acknowledged
`stored` writes receive automatic TTL expiry. Expired objects move to `deleting`;
their charge is released only after verified absence of the exact managed key.
Unknown deletion outcomes retain the charge and can be retried by the sweeper.

Ambiguous `pending` writes never expire automatically. A late remote PUT can
arrive after an absence observation, so age or a single HEAD/list result cannot
justify releasing capacity. For operator reconciliation, first fence and drain
all writers and outstanding remote requests, preserve the ledger and inventory
evidence, and establish the exact object's final state. There is no automated
pending-release command. Do not delete rows merely to restore upload capacity;
escalate for a reviewed, fenced reconciliation procedure.

The quota covers payload bytes in the managed namespace, not database metadata,
filesystem allocation overhead, or other bucket contents. S3 quarantine requires
confirmed disabled bucket versioning; enabled, suspended, and unknown versioning
states refuse persistence. Historical object versions are outside this quota.

## Deployment boundary

Drain old application writers before introducing ledger-backed writers. Apply
migration `202610200001` through the ordinary PostgreSQL migration flow before
starting the new API processes. Its declared irreversible boundary preserves
charges for objects that may still exist; schema downgrade across that boundary
is refused. A rollback must preserve the ledger and keep pre-ledger writers
fenced. This runbook authorizes no production cutover or manual database edit.

The filesystem backend requires a trusted application/deployment write boundary
on the static volume. Existing path and symlink checks do not provide atomic
protection against a hostile local process concurrently renaming entries or
swapping symlinks. Do not enable quarantine persistence on a volume writable by
untrusted local actors until that stronger boundary is established.

Code, tests, and current acceptance limits are tracked in the
[audit register](../audits/AUDIT-2026-10.md) and [MVP status](../superpowers/plans/STATUS.md).
