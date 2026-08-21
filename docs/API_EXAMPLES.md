# API Examples

This document provides request/response examples for the University Ecosystem API.

## Authentication

### Login

**Request:**
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "student@university.edu",
  "password": "SecurePass123!",
  "trust_device": false
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "student@university.edu",
    "full_name": "John Doe",
    "role": "student",
    "avatar_url": "/static/avatars/1.jpg",
    "mfa_enabled": true
  }
}
```

**Response (202 Accepted - MFA Required):**
```json
{
  "status": "mfa_required",
  "user_id": 1,
  "default_method": "totp",
  "methods": [
    {
      "method": "totp",
      "challenge_token": "abc123...",
      "challenge_expires_at": "2024-12-28T12:00:00Z",
      "remaining_attempts": 3
    }
  ]
}
```

### Register

**Request:**
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "newuser@university.edu",
  "password": "SecurePass123!",
  "full_name": "Jane Smith"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 2,
    "email": "newuser@university.edu",
    "full_name": "Jane Smith",
    "role": "student"
  }
}
```

## Events

### List Events

**Request:**
```http
GET /api/v1/events?page=1&size=20
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": 1,
      "title": "University Festival",
      "description": "Annual celebration event",
      "start_date": "2024-12-30T10:00:00Z",
      "end_date": "2024-12-30T18:00:00Z",
      "location": "Main Campus",
      "image_url": "/static/events/1.jpg",
      "organizer_id": 5,
      "registered_count": 150
    }
  ],
  "total": 45,
  "page": 1,
  "size": 20,
  "pages": 3
}
```

### Register for Event

**Request:**
```http
POST /api/v1/events/1/register
Authorization: Bearer <token>
```

**Response (201 Created):**
```json
{
  "event_id": 1,
  "user_id": 1,
  "registered_at": "2024-12-28T10:30:00Z",
  "status": "confirmed"
}
```

## Notifications

### Get User Notifications

**Request:**
```http
GET /api/v1/notifications?unread_only=true
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "notif_abc123",
      "type": "event_reminder",
      "title": "Event Starting Soon",
      "body": "University Festival starts in 1 hour",
      "created_at": "2024-12-30T09:00:00Z",
      "read": false,
      "action_url": "/events/1"
    },
    {
      "id": "notif_def456",
      "type": "news.comment",
      "title": "New Comment",
      "body": "John Doe commented on 'Spring Semester Updates'",
      "created_at": "2024-12-30T10:15:00Z",
      "read": false,
      "action_url": "/news/123#comment-456"
    }
  ],
  "total": 6,
  "unread_count": 4
}
```

## Error Responses

### Validation Error (422)
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

### Rate Limit Exceeded (429)
```json
{
  "detail": "Too many requests"
}
```
Headers: `Retry-After: 60`

### Unauthorized (401)
```json
{
  "detail": "Invalid credentials"
}
```
