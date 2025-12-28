# ADR-004: Notification System Architecture

## Status
Accepted

## Context
The platform needs a robust notification system to inform users about events, news, and other updates. Key requirements:
- Multi-channel delivery (in-app, Web Push)
- Deduplication to prevent spam
- Localization (Russian/English)
- Reliable delivery tracking

## Decision
We implement a notification system with the following components:

### Models
- **Notification**: Core entity with `dedupe_key` for preventing duplicates, `title`/`body` with `_en` variants
- **NotificationDelivery**: Tracks delivery attempts per channel with partitioned storage
- **NotificationQueueJob**: Background job queue for async processing
- **PushSubscription**: Web Push subscription storage

### API Flow
1. Notification created via service
2. Queue job enqueued for async delivery
3. Delivery service processes in background
4. Status tracked in NotificationDelivery

### Repository Pattern
`NotificationRepository` provides:
- `get_for_user()` with unread filtering
- `count_unread()` for badge counts
- `mark_as_read()` batch operations
- `get_by_dedupe_key()` for duplicate detection

## Consequences
**Positive:**
- Decoupled delivery from creation
- Easy to add new channels
- Reliable tracking and retry logic

**Negative:**
- Additional complexity vs synchronous delivery
- Requires background worker infrastructure
