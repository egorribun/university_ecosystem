# ADR 002: Dead Letter Queue for Background Jobs

**Status**: Accepted  
**Date**: 2024-12-18

## Context

Background job processing (notifications, email, etc.) can fail due to:

- External service outages
- Transient network errors
- Data validation issues
- Rate limiting

Without proper handling, failed jobs are lost, leading to:

- Missing notifications
- Data inconsistency
- No visibility into failure patterns

## Decision

Implement a Dead Letter Queue (DLQ) system with the following features:

### 1. Job Storage Model

```python
class DeadLetterJob:
    job_type: str           # Category of job
    job_hash: str           # SHA256 for deduplication
    payload: str            # JSON serialized job data
    error_message: str      # Last error
    retry_count: int        # Current retry attempt
    max_retries: int        # Maximum retry attempts (default: 3)
    status: JobStatus       # pending, retrying, failed, completed
    next_retry_at: datetime # When to retry next
```

### 2. Deduplication

Jobs are deduplicated by computing a hash of `(job_type, payload)`:

```python
def compute_job_hash(job_type: str, payload: dict) -> str:
    content = json.dumps({"type": job_type, "payload": payload}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()
```

### 3. Exponential Backoff

Retry delays follow exponential backoff:
- Attempt 1: 60 seconds
- Attempt 2: 120 seconds
- Attempt 3: 240 seconds
- Max: 3600 seconds (1 hour)

### 4. Admin API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/dlq/stats` | GET | Queue statistics by status |
| `/admin/dlq/jobs` | GET | List jobs with filtering |
| `/admin/dlq/retry/{id}` | POST | Manual retry trigger |
| `/admin/dlq/cleanup` | DELETE | Remove old completed jobs |

## Consequences

### Positive
- No job loss on transient failures
- Visibility into failure patterns
- Manual intervention capability
- Automatic recovery with backoff

### Negative
- Additional database table
- Cleanup maintenance required
- Monitoring dashboard needed

### Neutral
- Admin-only access for DLQ endpoints
- Completed jobs retained for 7 days by default
