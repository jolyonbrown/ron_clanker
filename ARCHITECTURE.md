# Ron Clanker Architecture - Database Strategy

## 🗄️ Current Database Setup (What's Actually Being Used)

### 1. **SQLite** - Primary Database ✅ ACTIVELY USED

**What it does:**
- Stores ALL application data
- Player statistics (743 players)
- Gameweek information (38 gameweeks)
- Ron's squad selections (GW8 team)
- DC analysis results
- Transfer decisions
- Historical data

**Why SQLite:**
- ✅ Perfect for single-instance applications
- ✅ No server overhead
- ✅ File-based (easy backups)
- ✅ Fast for our data size (~300KB)
- ✅ Zero configuration
- ✅ Bundled with Python

**Location:** `data/ron_clanker.db`

**Code:** `data/database.py` - Database class

### 2. **Redis** - Event Bus & Cache ✅ ACTIVELY USED

**What it does:**
- **Event Bus**: Agents publish/subscribe to events (pub/sub)
  - Scout publishes INJURY_INTELLIGENCE events
  - Hugo subscribes to injury events
  - All inter-agent communication goes through Redis
- **Caching**: Maggie (data collector) caches FPL API responses
  - Reduces API calls
  - Faster repeated queries
  - Respects rate limits

**Why Redis:**
- ✅ Purpose-built for pub/sub messaging
- ✅ Extremely fast (in-memory)
- ✅ Perfect for event-driven architecture
- ✅ Built-in pub/sub primitives
- ✅ Lightweight

**Container:** `ron_redis` (Docker)

**Code:** `infrastructure/event_bus.py` - EventBus class

### 3. **Postgres** - NOT CURRENTLY USED ❌

**Status:** Running but not used

**Why it exists:**
- Originally planned for production scalability
- Set up "just in case" we need it
- Left in docker-compose.yml for future

**Should we keep it?**
- ❌ Not needed for current functionality
- ❌ Uses resources unnecessarily
- ✅ Can be removed without breaking anything
- ✅ Can add back later if needed

---

## 🎯 Recommended Action: Remove Postgres

**Test Results:**
```bash
# Stopped Postgres container
$ docker stop ron_postgres

# Tested full system
✓ Database works: 743 players
✓ Scout works
✓ Hugo works
✓ Redis works
✅ Everything works WITHOUT Postgres!
```

**What to do:**
1. Stop and remove Postgres container
2. Update docker-compose.yml to comment out Postgres
3. Save ~128MB RAM
4. Keep it documented for Phase 3 if needed

---

## 📊 Database Strategy by Phase

### Phase 1-2 (CURRENT): SQLite + Redis ✅

```
┌─────────────────────────────────────┐
│         Ron Clanker System          │
├─────────────────────────────────────┤
│                                     │
│  Agents (Python scripts)            │
│  ├─ Scout                           │
│  ├─ Hugo                            │
│  ├─ Maggie                          │
│  └─ All Analysts                    │
│       │                             │
│       ├─► SQLite (data storage)    │
│       │   • Players, gameweeks      │
│       │   • Decisions, transfers    │
│       │   • File: ron_clanker.db    │
│       │                             │
│       └─► Redis (event bus + cache)│
│           • Pub/sub messaging       │
│           • FPL API cache           │
│           • Container: ron_redis    │
│                                     │
└─────────────────────────────────────┘
```

**Characteristics:**
- Simple
- Fast
- Low resource usage
- Perfect for development
- Perfect for single RPi deployment
- Zero overhead

### Phase 3 (FUTURE): Consider Postgres

**When you MIGHT want Postgres:**

1. **Multiple FPL Teams**
   - Managing 10+ teams
   - Need concurrent access
   - SQLite locks on writes

2. **Advanced Analytics**
   - Complex queries across millions of rows
   - Time-series analysis
   - ML feature extraction

3. **Multi-Server Deployment**
   - Deploying to multiple machines
   - Need centralized database
   - Docker Swarm/Kubernetes

4. **Team Collaboration**
   - Multiple developers
   - Shared database access
   - Need ACID guarantees

**When you DON'T need Postgres (now):**
- ✅ Single FPL team (Ron's team)
- ✅ Single server (RPi)
- ✅ Data size < 1GB (currently 300KB!)
- ✅ Simple queries (they're instant)
- ✅ One user (you!)

---

## 🔧 Migration Path (If Needed Later)

If you ever need to migrate from SQLite to Postgres:

1. **Export data:**
   ```bash
   sqlite3 data/ron_clanker.db .dump > backup.sql
   ```

2. **Convert schema:**
   - Update `data/schema.sql` for Postgres syntax
   - Minor changes (AUTOINCREMENT → SERIAL, etc.)

3. **Update Database class:**
   - Change connection from `sqlite3` to `psycopg2`
   - Rest of code stays the same (uses same SQL)

4. **Import data:**
   ```bash
   psql ron_clanker < backup.sql
   ```

**Effort:** 1-2 hours (straightforward)

---

## 💡 Simplified Docker Compose (Recommended)

Current setup:
```yaml
services:
  redis:     ✅ KEEP (event bus + cache)
  postgres:  ❌ REMOVE (not used)
  # Celery, agents: Not needed yet (agents run as scripts)
```

Recommended minimal setup:
```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    mem_limit: 128m
```

**Benefits:**
- Cleaner architecture
- Less confusion
- Saves 128MB RAM
- Faster startup
- Easier to understand

---

## ✅ Summary: What Each Database Does

| Database | Used? | Purpose | Size | Location |
|----------|-------|---------|------|----------|
| **SQLite** | ✅ YES | All data storage | 300KB | `data/ron_clanker.db` |
| **Redis** | ✅ YES | Event bus + cache | ~10MB | Container: `ron_redis` |
| **Postgres** | ❌ NO | Nothing (future?) | 0 | Container: `ron_postgres` (can remove) |

**Recommendation**: Remove Postgres, keep SQLite + Redis. Add Postgres back in Phase 3 if truly needed (unlikely).

**Ron's take**: "Keep it simple. SQLite and Redis do the job perfectly. Why complicate things?" 🎯
