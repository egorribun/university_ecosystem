# Disaster Recovery Guide

This document describes procedures for recovering the University Ecosystem PostgreSQL database from backups.

## Backup Strategy Overview

| Component | Frequency | Retention | Storage |
|-----------|-----------|-----------|---------|
| Base Backups | Daily 2:00 AM UTC | 7 days | S3/MinIO |
| WAL Archives | Continuous | 7 days | S3/MinIO |
| Backup Verification | Weekly Sunday 4:00 AM | N/A | N/A |

## Recovery Scenarios

### 1. Point-in-Time Recovery (PITR)

Restore to a specific point in time using base backup + WAL replay.

```bash
# 1. Stop the PostgreSQL pod
kubectl scale deployment postgres --replicas=0 -n university-ecosystem

# 2. Download the base backup closest to (but before) target time
export BACKUP_NAME="base_backup_20260127_020000"
export S3_BUCKET="university-ecosystem-backups"
export TARGET_TIME="2026-01-27 15:30:00 UTC"

aws s3 cp "s3://${S3_BUCKET}/postgres-backups/${BACKUP_NAME}/" /restore/ --recursive

# 3. Extract backup to data directory
cd /var/lib/postgresql/data
rm -rf *
tar -xzf /restore/base.tar.gz

# 4. Create recovery configuration
cat > postgresql.auto.conf << EOF
restore_command = 'aws s3 cp s3://${S3_BUCKET}/postgres-backups/wal/%f.gz - | gunzip > %p'
recovery_target_time = '${TARGET_TIME}'
recovery_target_action = 'promote'
EOF

# 5. Create recovery signal file
touch recovery.signal

# 6. Start PostgreSQL
kubectl scale deployment postgres --replicas=1 -n university-ecosystem

# 7. Monitor recovery progress
kubectl logs -f deployment/postgres -n university-ecosystem
```

### 2. Full Database Restore

Restore the latest complete backup.

```bash
# 1. Identify latest backup
aws s3 ls "s3://${S3_BUCKET}/postgres-backups/" | sort | tail -1

# 2. Follow PITR steps 1-3 above

# 3. Start without recovery target (restores all available WAL)
cat > postgresql.auto.conf << EOF
restore_command = 'aws s3 cp s3://${S3_BUCKET}/postgres-backups/wal/%f.gz - | gunzip > %p || exit 1'
recovery_target_action = 'promote'
EOF

touch recovery.signal

# 4. Start PostgreSQL
kubectl scale deployment postgres --replicas=1 -n university-ecosystem
```

### 3. Disaster Recovery to New Cluster

Complete cluster restoration in a new environment.

```bash
# 1. Create new PostgreSQL deployment
kubectl apply -f deploy/postgres/

# 2. Wait for pod to be ready (but not initialized)
kubectl wait --for=condition=Ready pod -l app=postgres -n university-ecosystem

# 3. Stop PostgreSQL in the new pod
kubectl exec -it deployment/postgres -n university-ecosystem -- \
  pg_ctl stop -D /var/lib/postgresql/data

# 4. Clear data directory and restore backup
kubectl exec -it deployment/postgres -n university-ecosystem -- bash -c '
  cd /var/lib/postgresql/data
  rm -rf *
  aws s3 cp s3://${S3_BUCKET}/postgres-backups/${BACKUP_NAME}/base.tar.gz - | tar -xz
'

# 5. Configure recovery and start
kubectl exec -it deployment/postgres -n university-ecosystem -- bash -c '
  cat > /var/lib/postgresql/data/postgresql.auto.conf << EOF
restore_command = '\''aws s3 cp s3://${S3_BUCKET}/postgres-backups/wal/%f.gz - | gunzip > %p'\''
recovery_target_action = '\''promote'\''
EOF
  touch /var/lib/postgresql/data/recovery.signal
  pg_ctl start -D /var/lib/postgresql/data
'

# 6. Run Alembic migrations to ensure schema is current
kubectl exec -it deployment/api -n university-ecosystem -- alembic upgrade head
```

## Verification Procedures

### Verify Backup Integrity

```bash
# Manual verification
kubectl create job --from=cronjob/postgres-backup-verify verify-now -n university-ecosystem
kubectl logs -f job/verify-now -n university-ecosystem
```

### Test Restore (Recommended Monthly)

1. Create a temporary PostgreSQL instance
2. Restore the latest backup
3. Run application health checks
4. Verify data integrity with checksums
5. Document results and cleanup

## Monitoring & Alerts

| Metric | Threshold | Action |
|--------|-----------|--------|
| Backup age | > 26 hours | Page on-call |
| Backup size anomaly | ±50% from baseline | Investigate |
| WAL archive lag | > 10 minutes | Warning alert |
| Verification failure | Any | Page on-call |

## Contact

- **On-call**: See PagerDuty escalation policy
- **Database Team**: #db-team on Slack
- **Security Incidents**: security@university.edu
