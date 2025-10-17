# Docker Setup Guide for Ron Clanker

## Overview

Ron Clanker runs entirely in Docker containers for easy deployment and portability. This guide explains how to set up and manage the containerized environment.

## Current Services

### Infrastructure Services
- **Redis** (redis:7-alpine) - Event bus and caching layer
- **Postgres** (postgres:15-alpine) - Persistent data storage

### Agent Services (Coming in Phase 2)
- Manager Agent (Ron Clanker)
- Data Collector Agent (Maggie)
- Analysis Agents (Digger, Sophia, Jimmy, Priya, etc.)

## Initial Setup

### 1. Environment Configuration

Copy the example environment file and set your passwords:

```bash
cp .env.example .env
```

Edit `.env` and set a secure password for `DB_PASSWORD`. **Never commit this file to git!**

Example `.env`:
```bash
DB_PASSWORD=your_secure_random_password_here
REDIS_URL=redis://redis:6379
POSTGRES_URL=postgresql://ron:${DB_PASSWORD}@postgres:5432/ron_clanker
LOG_LEVEL=INFO
```

### 2. Start Services

Start all infrastructure services:

```bash
docker compose up -d
```

This will:
- Pull required images (first time only)
- Create persistent volumes for data
- Start Redis and Postgres containers
- Run health checks

### 3. Verify Services

Check that all services are healthy:

```bash
docker compose ps
```

You should see:
```
NAME           IMAGE                STATUS
ron_postgres   postgres:15-alpine   Up (healthy)
ron_redis      redis:7-alpine       Up (healthy)
```

View logs for any service:
```bash
docker logs ron_redis
docker logs ron_postgres
```

## Service Management

### Stop All Services
```bash
docker compose down
```

### Stop and Remove Volumes (⚠️ Deletes all data!)
```bash
docker compose down -v
```

### Restart a Service
```bash
docker compose restart redis
docker compose restart postgres
```

### Update Images
```bash
docker compose pull
docker compose up -d
```

## Connecting to Services

### Redis
From host machine:
```bash
redis-cli -p 6379
```

From Python:
```python
import redis
client = redis.Redis(host='localhost', port=6379)
```

### Postgres
From host machine:
```bash
# Get password from .env file first
docker exec -it ron_postgres psql -U ron -d ron_clanker
```

From Python:
```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='ron_clanker',
    user='ron',
    password=os.getenv('DB_PASSWORD')
)
```

## Data Persistence

Data is stored in Docker volumes:
- `ron_clanker_redis_data` - Redis cache and event data
- `ron_clanker_postgres_data` - Postgres database files

These volumes persist across container restarts. To back up:

```bash
# Backup Postgres
docker exec ron_postgres pg_dump -U ron ron_clanker > backup.sql

# Restore Postgres
docker exec -i ron_postgres psql -U ron ron_clanker < backup.sql
```

## Resource Limits

Configured for Raspberry Pi 3B:
- Redis: 128MB memory limit, 100MB cache size
- Postgres: 256MB memory limit

These can be adjusted in `docker-compose.yml` for more powerful hardware.

## Troubleshooting

### Container won't start
Check logs:
```bash
docker compose logs <service-name>
```

### Port already in use
Check what's using the port:
```bash
sudo lsof -i :6379  # Redis
sudo lsof -i :5432  # Postgres
```

### Out of disk space
Clean up old images and containers:
```bash
docker system prune -a
```

### Health check failing
Wait 10-30 seconds for services to fully start, especially Postgres.

### Permission errors
Ensure the user running docker has proper permissions:
```bash
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

## Security Notes

### ✅ Proper Security
- Passwords stored in `.env` file (not committed to git)
- `.env` is in `.gitignore`
- Services only accessible from localhost by default
- Secure random passwords generated

### ❌ What NOT to Do
- Never commit `.env` to git
- Never use default/weak passwords
- Never expose ports publicly without authentication
- Never share your `.env` file

## Migration from System Services

If you were running Redis/Postgres as system services:

### Stop system services
```bash
sudo systemctl stop redis
sudo systemctl stop postgresql
sudo systemctl disable redis
sudo systemctl disable postgresql
```

### Migrate data (optional)
Export from system service, import to container (see Data Persistence section).

### Update application configs
Change connection strings from:
- `localhost:6379` → `redis:6379` (when running inside containers)
- `localhost:6379` → `localhost:6379` (when running on host)

## Next Steps

Once infrastructure is stable:
1. **Phase 2**: Add agent containers (Maggie, Digger, etc.)
2. **Phase 3**: Add Celery worker for scheduled tasks
3. **Phase 4**: Add monitoring (Prometheus/Grafana)

## Quick Reference

```bash
# Start everything
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# Stop everything
docker compose down

# Update and restart
docker compose pull && docker compose up -d

# Shell access
docker exec -it ron_redis redis-cli
docker exec -it ron_postgres psql -U ron -d ron_clanker
```

---

**Last Updated**: October 10th, 2025
**Tested On**: Raspberry Pi 3B (ARM64)
**Docker Compose Version**: 2.x+
