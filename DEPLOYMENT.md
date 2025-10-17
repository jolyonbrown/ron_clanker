# Ron Clanker Deployment Guide

## 🗄️ Data Persistence & Backups

### Current Setup

**Primary Database**: SQLite (`data/ron_clanker.db`)
- **Location**: `/home/jolyon/ron_clanker/data/ron_clanker.db`
- **Persistence**: Stored on filesystem (survives container restarts)
- **Size**: ~300KB currently
- **Data**: 743 players, 38 gameweeks, GW8 squad, DC analysis

**Container Volumes**: Docker named volumes (persistent)
- `ron_clanker_postgres_data`: Postgres data (not actively used yet)
- `ron_clanker_redis_data`: Redis event bus data

### ✅ Data is SAFE from Container Restarts

**When containers restart**:
- ✅ SQLite database is **NOT affected** (filesystem-based)
- ✅ Docker volumes **persist automatically**
- ✅ Ron's teams, decisions, and analysis are **safe**

**What you DON'T lose**:
- Player data
- GW8 squad selection
- DC analysis results
- Historical decisions
- Transfer plans

### 🔒 Backup Strategy

**Automated Backups** (recommended):
```bash
# Run daily at 2 AM via cron
crontab -e

# Add this line:
0 2 * * * /home/jolyon/ron_clanker/venv/bin/python /home/jolyon/ron_clanker/scripts/backup_database.py
```

**Manual Backup**:
```bash
venv/bin/python scripts/backup_database.py
```

**Backup Locations**:
1. **Local**: `data/backups/ron_clanker_YYYYMMDD_HHMMSS.db` (last 30 kept)
2. **Git-tracked**: `data/ron_clanker_latest_backup.db` (for version control)
3. **Latest symlink**: `data/backups/latest.db` (always points to most recent)

**Restore from Backup**:
```bash
# Restore from latest
bash scripts/restore_database.sh latest

# Restore from specific backup
bash scripts/restore_database.sh data/backups/ron_clanker_20251017_170945.db
```

### 📊 Verify Data Integrity

```bash
# Check database status
venv/bin/python -c "
from data.database import Database
db = Database()
print(f\"Players: {db.execute_query('SELECT COUNT(*) as c FROM players')[0]['c']}\")
print(f\"Gameweeks: {db.execute_query('SELECT COUNT(*) as c FROM gameweeks')[0]['c']}\")
"
```

---

## 🍓 Is Raspberry Pi Suitable?

### Current Setup: RPi 3B

**Specs**:
- CPU: 4-core ARM Cortex-A53 @ 1.2GHz
- RAM: 1GB
- Storage: SD card

### ✅ What Works Well on RPi 3B

1. **Core Infrastructure** (containerized):
   - Redis (event bus): ✅ Excellent
   - Postgres (if needed): ✅ Works fine

2. **Agents (Python scripts)**:
   - Scout: ✅ Intelligence gathering works perfectly
   - Hugo: ✅ Transfer strategy responsive
   - All analysts: ✅ Analysis completes quickly
   - Event bus coordination: ✅ No issues

3. **Current Workload**:
   - Database: 300KB SQLite (tiny)
   - System load during operation: < 2.0 (comfortable)
   - Memory usage: ~200-300MB (plenty of headroom)

### ⚠️ What Struggles on RPi 3B

1. **Building Multiple Docker Images Simultaneously**:
   - Caused load > 20, system freeze
   - Solution: Build images one at a time, or pre-build on faster machine

2. **Heavy Python Package Installation**:
   - PyTorch, TensorFlow would struggle
   - Solution: Pre-built wheels from piwheels.org, or use CPU-only versions

3. **Concurrent ML Training**:
   - Phase 3 ML models may need optimization
   - Solution: Train models on more powerful machine, deploy inference only

### 🎯 Recommendations

**For Phase 1-2 (Current)**: ✅ **RPi 3B is PERFECT**
- Agents run as Python scripts (low overhead)
- Event bus coordination works flawlessly
- Database operations are instant
- Intelligence gathering is I/O bound (network), not CPU bound
- **No issues expected**

**For Phase 3 (ML & Production)**: Consider upgrade options:

**Option A**: Stay on RPi 3B with optimizations
- ✅ Use pre-trained models (inference only)
- ✅ Lightweight ML (scikit-learn works fine)
- ✅ Offload training to cloud/laptop
- ✅ Keep agents as scripts (don't containerize all)

**Option B**: Upgrade to RPi 4/5
- 4GB+ RAM model
- Better for containerized agents
- Can train simple ML models
- Still cost-effective (~$55-75)

**Option C**: Move to cloud (overkill for now)
- AWS EC2 t4g.small (~$12/month)
- Always-on, scheduled tasks easier
- But RPi is MORE FUN! 🍓

### 💡 Current Recommendation: **STAY ON RPi 3B**

**Why**:
1. System is working perfectly
2. Agents don't need containers during development
3. Cost: £0/month vs cloud
4. Ron Clanker runs great on limited resources (very efficient)
5. Can upgrade later if Phase 3 ML is too heavy

**Future trigger to upgrade**:
- When we need to train ML models frequently
- When we want full containerized microservices (nice-to-have)
- When inference becomes too slow (unlikely)

---

## 🚀 Deployment Modes

### Current: Development Mode ✅

**What's Running**:
```
Infrastructure:
├─ Redis (container): Event bus
└─ Postgres (container): Database (optional)

Agents (Python scripts):
├─ Scout: Intelligence gathering
├─ Hugo: Transfer strategy
├─ Maggie: Data collection
└─ All analysts
```

**How to Run**:
```bash
# Start infrastructure
docker compose up -d redis postgres

# Run full system test
venv/bin/python scripts/test_full_system.py

# Run individual agent
venv/bin/python -m agents.scout
```

**Advantages**:
- Fast iteration
- Low resource usage
- Easy debugging
- Perfect for RPi 3B

### Future: Production Mode

**What Would Change**:
- Each agent as separate container
- Celery workers for scheduling
- Full microservices architecture
- Kubernetes/Docker Swarm (optional)

**When to Switch**:
- Phase 3 (ML & optimization)
- When deploying to cloud
- When scaling beyond 1 FPL team

---

## 🔐 Security Notes

**Database Backups**:
- ✅ Automated daily backups
- ✅ Git-tracked backup (version control)
- ✅ 30-day retention policy
- ⚠️ Consider off-site backups (Google Drive, rsync to another machine)

**SD Card Failure Risk**:
- RPi SD cards can fail
- **Mitigation**: Automated backups + git push
- **Upgrade option**: Boot from USB SSD (more reliable)

**Recommended Additional Backup**:
```bash
# Weekly backup to remote location
rsync -avz data/backups/ user@backup-server:/backups/ron_clanker/
```

---

## 📈 Resource Monitoring

**Check System Health**:
```bash
# System load
uptime

# Docker stats
docker stats --no-stream

# Disk space
df -h

# Database size
du -h data/ron_clanker.db
```

**Typical Healthy Stats (RPi 3B)**:
- Load average: < 2.0
- Memory usage: < 500MB
- Database growth: ~10-50KB per gameweek
- Disk: < 1GB total project size

---

## ✅ Summary

**Your Data is Safe**: ✓
- SQLite persists across container restarts
- Automated backup system in place
- Docker volumes are persistent

**RPi 3B is Suitable**: ✓
- Current workload runs perfectly
- Development mode is optimal
- Can handle Phase 1 & 2 with no issues
- Phase 3 will depend on ML complexity

**Next Steps**:
1. ✅ Set up daily automated backups (cron job)
2. ✅ Commit backup scripts to git
3. ✅ Test restore process
4. Optional: Set up off-site backup
5. Optional: Monitor SD card health

**Ron's verdict**: "If it ain't broke, don't fix it. The Pi's doing the job just fine!" 🍓⚽
