---
description: How to deploy the university ecosystem application
---
# Deployment Workflow

// turbo-all

This document outlines the steps to deploy the University Ecosystem application.

## Prerequisites

- SSH access to the production server
- Docker and Docker Compose installed
- PostgreSQL and Redis instances running

## 1. Pull Latest Changes

```powershell
git pull origin main
```

## 2. Run Database Migrations

Always backup your database before running migrations.

```powershell
alembic upgrade head
```

## 3. Rebuild and Start Services

```powershell
docker-compose up --build -d
```

## 4. Verify Deployment

Check the health endpoint to ensure the application is running correctly.

```powershell
curl http://localhost:8000/health
```

## 5. Post-Deployment Maintenance

The `PartitionManager` and `CacheWarmupService` will automatically run on startup. Monitor logs for any initialization errors.

```powershell
docker-compose logs -f app
```
