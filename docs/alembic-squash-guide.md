# TD-20-02: Alembic Migration Squash Strategy

**Audit ID**: TD-20-02
**Date**: 2026-03-24
**Priority**: MEDIUM
**Estimated effort**: 4 hours (DBA + DevOps pair)

---

## Problem Statement

The project has accumulated **111 migration files** in `alembic/versions/`, spanning from the initial schema (`b05ae64aaeef_init.py`, 2025-05-29) to the latest additions. This causes:

1. **Slow `alembic upgrade head`**: Fresh deployments on CI/staging iterate through 111 sequential DDL files (~45-90 seconds depending on DB latency).
2. **Complex dependency graph**: Mix of hex-hash revisions (legacy) and date-prefixed revisions (modern convention) makes the chain fragile.
3. **Merge migrations**: Files like `d0b0cb4c1910_merge_data_access_logs_head.py` and `ffe470bc9ca2_merge_quiet_hours_push_subscriptions.py` indicate past branch conflicts.
4. **Developer friction**: Understanding the migration history requires reading 111 files.

## Squash Strategy

### Pre-conditions (MUST verify before squash)

```bash
# 1. Ensure ALL production databases are at head
alembic current  # Must show latest revision

# 2. Dump current schema as ground truth
pg_dump --schema-only --no-owner --no-privileges \
  -f schema_before_squash.sql "$DATABASE_URL"

# 3. Tag the current head in git
git tag pre-squash-$(alembic heads | head -1)
```

### Step 1: Generate squashed baseline

```bash
# Create a fresh migration from current models
# This captures the FULL schema as a single migration
alembic revision --autogenerate \
  -m "squash_baseline_$(date +%Y%m%d)" \
  --rev-id "squash_baseline_001"
```

### Step 2: Archive old migrations

```bash
# Move old migrations to archive (don't delete — needed for rollback)
mkdir -p alembic/versions/_archived_pre_squash
mv alembic/versions/b05ae64aaeef_*.py alembic/versions/_archived_pre_squash/
mv alembic/versions/[0-9a-f]*_*.py alembic/versions/_archived_pre_squash/
mv alembic/versions/20250[0-9]*_*.py alembic/versions/_archived_pre_squash/
# Keep only the squashed baseline
```

### Step 3: Stamp existing databases

```bash
# On EVERY production/staging database:
# This tells Alembic "you're already at the squash baseline"
# without actually running the migration DDL
alembic stamp squash_baseline_001
```

### Step 4: Verify

```bash
# Dump schema after squash baseline and diff
pg_dump --schema-only --no-owner --no-privileges \
  -f schema_after_squash.sql "$DATABASE_URL"

diff schema_before_squash.sql schema_after_squash.sql
# Must be empty (no diff)

# Verify fresh deployment works
docker compose run --rm backend alembic upgrade head
```

## Safety Checklist

- [ ] All production databases confirmed at `head` before squash
- [ ] Schema dump taken and stored in artifact storage
- [ ] Git tag created at pre-squash commit
- [ ] Squashed baseline reviewed by 2 engineers
- [ ] All environments stamped with new baseline
- [ ] CI pipeline updated to use squashed history
- [ ] Old migrations archived (not deleted)
- [ ] Fresh `alembic upgrade head` tested on empty database
- [ ] Rollback procedure documented and tested

## Rollback Procedure

If squash causes issues:

```bash
# 1. Restore old migrations from archive
mv alembic/versions/_archived_pre_squash/*.py alembic/versions/

# 2. Remove squash baseline
rm alembic/versions/squash_baseline_001_*.py

# 3. Stamp databases back to original head
alembic stamp <original_head_revision>
```

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Migration files | 111 | 1 (baseline) + incremental |
| Fresh `upgrade head` time | ~60s | ~3s |
| Dependency chain complexity | 111 nodes, 2 merges | 1 node |
| Developer onboarding friction | High | Low |

## Convention Going Forward

After squash, enforce date-prefix naming via `alembic.ini`:

```ini
# Uncomment and set in alembic.ini:
file_template = %%(year)d%%(month).2d%%(day).2d%%(hour).2d%%(minute).2d_%%(slug)s
```

This ensures chronological ordering and prevents hex-hash collisions on feature branches.
