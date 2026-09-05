# Revenue Leak Radar — Database Deployment Guide

---

## Local Development (SQLite)

No setup needed. The existing `revenue_radar.db` in `backend/` is your local database.

```
backend/.env:
DATABASE_URL=sqlite+aiosqlite:///./revenue_radar.db
DATABASE_URL_SYNC=sqlite:///./revenue_radar.db
```

**IMPORTANT:** `revenue_radar.db` is excluded from git by `.gitignore` and must never be committed or copied to production.

---

## Production Database: PostgreSQL

Revenue Leak Radar is already configured for PostgreSQL. The `asyncpg` and `psycopg2-binary` drivers are installed.

### Option A: Render Managed PostgreSQL (Recommended)

1. Log into [render.com](https://render.com)
2. Click **New → PostgreSQL**
3. Name it: `revenue-radar-db`
4. Plan: **Starter** (free tier) or **Standard** for production
5. Click **Create Database**
6. Copy the **External Database URL** — it will look like:
   ```
   postgresql://revenue_radar:PASSWORD@HOST.oregon-postgres.render.com/revenue_radar
   ```

### Option B: Supabase / Neon / Railway

Any managed PostgreSQL service works. You'll need the connection strings:
- **Async URL** (for the app): `postgresql+asyncpg://USER:PASS@HOST:5432/DB`
- **Sync URL** (for Alembic): `postgresql://USER:PASS@HOST:5432/DB`

---

## Configuring the Backend for PostgreSQL

In Render backend environment variables (or your `.env`):

```
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/revenue_radar
DATABASE_URL_SYNC=postgresql://USER:PASSWORD@HOST:5432/revenue_radar
```

---

## Running Migrations Against Production

Once you have a production PostgreSQL database and `DATABASE_URL_SYNC` is set:

```bash
cd backend
# Activate venv (local) or just run in Render shell
alembic upgrade head
```

This applies all 3 migrations in order:
1. `7f42829f8e13` — Initial schema (all tables)
2. `9c1f4e7a2b5d` — Timestamp defaults fix
3. `c3d9f1a2b4e7` — Lead lifecycle + detector columns

The migrations are **additive only** — they never drop tables or delete data.

---

## Demo Data (First Deploy)

After migrations, seed the demo organization data:

```bash
cd backend
python -m scripts.seed_demo_data
```

**The seed script is idempotent** — safe to run multiple times. It checks for the demo organization first and exits early if already seeded.

---

## Application Startup (Auto-Table Creation)

On every startup, `app/main.py` runs `Base.metadata.create_all()` which:
- Creates any missing tables
- Is **additive only** — never drops or truncates

This means after migrations, the app will start cleanly on a fresh PostgreSQL database.

---

## Database Safety Rules

| Command | Should Run? | Notes |
|---------|-------------|-------|
| `alembic upgrade head` | ✅ Yes | Safe — additive migrations only |
| `python -m scripts.seed_demo_data` | ✅ Yes (once) | Idempotent seed |
| `alembic downgrade` | ⚠️ Review first | Reverses schema changes |
| `Base.metadata.drop_all()` | ❌ Never in prod | Only in dev reset scripts |
| Manual `DROP TABLE` | ❌ Never | Could destroy all data |

---

## Backup Strategy

For Render PostgreSQL:
- **Automatic daily backups** are included with Standard plan
- **Manual backup**: `pg_dump $DATABASE_URL > backup.sql`
- **Restore**: `psql $DATABASE_URL < backup.sql`

---

## Switching from SQLite to PostgreSQL Locally

If you want to test PostgreSQL locally:

```bash
# Start local PostgreSQL via Docker:
docker compose up -d

# Update backend/.env:
DATABASE_URL=postgresql+asyncpg://revenue_radar:revenue_radar@localhost:5432/revenue_radar
DATABASE_URL_SYNC=postgresql://revenue_radar:revenue_radar@localhost:5432/revenue_radar

# Run migrations:
cd backend
alembic upgrade head

# Seed data:
python -m scripts.seed_demo_data
```
