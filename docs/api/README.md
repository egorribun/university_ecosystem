# University Ecosystem API Documentation

## Overview

The University Ecosystem API provides RESTful endpoints for managing university platform features including events, news, schedules, messaging, and notifications.

**Base URL**: `/api/v1`

**Authentication**: Bearer token (JWT) required for most endpoints.

---

## API Sections

### Public Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/public/news` | GET | Public news feed |

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/login` | POST | User login |
| `/auth/register` | POST | User registration |
| `/auth/logout` | POST | Session logout |
| `/auth/refresh` | POST | Token refresh |
| `/auth/forgot-password` | POST | Password reset request |

### Events

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events` | GET | List events (cursor pagination) |
| `/events/{id}` | GET | Get event details |
| `/events` | POST | Create event (admin) |
| `/events/{id}` | PUT | Update event (admin) |
| `/events/{id}` | DELETE | Delete event (admin) |
| `/events/{id}/attend` | POST | Register attendance |
| `/events/{id}/unattend` | POST | Cancel attendance |

### News

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/news` | GET | List news articles |
| `/news/{id}` | GET | Get news article |
| `/news` | POST | Create news (admin) |
| `/news/{id}` | PUT | Update news (admin) |
| `/news/{id}` | DELETE | Delete news (admin) |

### Schedule

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/schedule` | GET | Get user schedule |
| `/schedule/group/{group_id}` | GET | Get group schedule |

### Chat / Messaging

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chats` | GET | List user chats |
| `/chats` | POST | Create new chat |
| `/chats/{id}` | GET | Get chat details |
| `/chats/{id}/messages` | GET | List messages (cursor pagination) |
| `/chats/{id}/messages` | POST | Send message |

### Notifications

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/notifications` | GET | List user notifications |
| `/notifications/{id}/read` | POST | Mark as read |
| `/notifications/read-all` | POST | Mark all as read |

### User Profile

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/users/me` | GET | Current user profile |
| `/users/me` | PATCH | Update profile |
| `/users/me/avatar` | POST | Upload avatar |

---

## Admin Endpoints

### User Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/users` | GET | List all users |
| `/users/{id}` | DELETE | Delete user |

### Dead Letter Queue (Internal)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/dlq/stats` | GET | DLQ statistics |
| `/admin/dlq/jobs` | GET | List DLQ jobs |
| `/admin/dlq/retry/{id}` | POST | Retry failed job |
| `/admin/dlq/cleanup` | DELETE | Cleanup old jobs |

---

## Pagination

The API uses **cursor-based pagination** for large collections:

```json
{
  "items": [...],
  "total": 150,
  "limit": 20,
  "cursor": "abc123",
  "next_cursor": "def456",
  "has_more": true
}
```

**Parameters**:
- `limit`: Number of items per page (default: 20, max: 100)
- `cursor`: Cursor from previous response for next page

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message description"
}
```

**HTTP Status Codes**:
- `400` - Bad Request (validation error)
- `401` - Unauthorized (missing/invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `422` - Unprocessable Entity
- `500` - Internal Server Error

---

## Localization

The API supports multiple languages via the `Accept-Language` header:

```
Accept-Language: ru
Accept-Language: en
Accept-Language: ar
```

Response will include translated content where available.

---

## Rate Limiting

API requests are rate-limited to protect service stability:
- **Authenticated requests**: 100 requests/minute
- **Unauthenticated requests**: 20 requests/minute

Rate limit headers are included in responses:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

---

## WebSocket

Real-time updates are available via WebSocket:

**Endpoint**: `wss://{host}/ws/chat`

**Authentication**:
- `Sec-WebSocket-Protocol: access_token, <JWT>`
- `Authorization: Bearer <JWT>`
- Cookie-based auth (`access_token_v2`)

Query-param tokens are supported only when the `websocket_query_param_compat`
feature flag is enabled.

**Events**:
- `chat.message` - New message in chat
- `notification` - New notification
- `presence` - User online status change

---

## OpenAPI Schema

Full OpenAPI schema available at:
- `/docs` - Swagger UI
- `/redoc` - ReDoc
- `/openapi.json` - Raw JSON schema
