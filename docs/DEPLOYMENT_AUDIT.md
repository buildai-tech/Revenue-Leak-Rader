# Revenue Leak Radar — Deployment Audit

**Date:** 2026-09-05  
**Engineer:** Production Deployment Audit  
**Workspace:** Revenue-Leakage-Deploy

---

## Actual Architecture Discovered

| Component | Technology |
|-----------|-----------|
| **Backend framework** | FastAPI 0.115.12 + Uvicorn 0.34.3 |
| **Backend language** | Python 3.11+ (local: 3.14.4) |
| **Frontend framework** | React 18 + Vite 6 + TypeScript 5.7 + TailwindCSS 3.4 |
| **Database (local)** | SQLite via aiosqlite (`revenue_radar.db`) |
| **Database (production-ready)** | PostgreSQL (asyncpg driver already installed) |
| **ORM** | SQLAlchemy 2.0 async |
| **Migrations** | Alembic 1.15.2 (3 migrations exist) |
| **AI Provider** | NVIDIA NIM (OpenAI-compatible) or NoOp fallback |
| **Package manager** | pip (backend), npm (frontend) |
| **Authentication** | None (V1 — single demo organization) |
| **Backend entrypoint** | `app.main:app` |
| **Backend startup cmd** | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1` |
| **Frontend build** | `npm run build` (output: `frontend/dist/`) |
| **Node version** | v20.20.2 |

---

## Database Files Found

| File | Location | Status |
|------|----------|--------|
| `revenue_radar.db` | `backend/revenue_radar.db` | ✅ Active — DO NOT delete |
| `revenue_radar.db` | repo root (symlink/copy) | Local — excluded by .gitignore |
| `revenue_radar.db.bak_before_timestamp_migration` | `backend/` | Backup — excluded by .gitignore |

---

## Alembic Migrations (3 total)

| Migration | Description |
|-----------|-------------|
| `7f42829f8e13` | Initial schema |
| `9c1f4e7a2b5d` | Fix SQLite timestamp defaults |
| `c3d9f1a2b4e7` | Add lead lifecycle and detector columns |

---

## Issues Found and Fixed

### 🔴 CRITICAL — Fixed
| Issue | File | Fix Applied |
|-------|------|-------------|
| **Real NVIDIA API key in .env.example** | `backend/.env.example` | Replaced with empty placeholder |

### 🟡 MEDIUM — Fixed
| Issue | File | Fix Applied |
|-------|------|-------------|
| No root `.gitignore` | Root | Created comprehensive `.gitignore` |
| No `Dockerfile` for backend | `backend/` | Created production `Dockerfile` |
| No `frontend/vercel.json` | `frontend/` | Created with SPA routing + security headers |
| No frontend env var for API URL | `frontend/src/lib/api.ts` | `VITE_API_URL` with `/api` fallback |
| Vite config hardcoded proxy target | `frontend/vite.config.ts` | Made configurable via `VITE_BACKEND_DEV_URL` |
| No TypeScript type for `import.meta.env` | `frontend/src/` | Created `vite-env.d.ts` |
| No PORT support for Render | `backend/app/config.py` | Added `PORT: int = 8000` |
| Stack traces in 500 responses | `backend/app/main.py` | Global exception handler with safe messages |
| `/docs` and `/redoc` exposed in prod | `backend/app/main.py` | Disabled when `APP_ENV=production` |
| Health endpoint not at `/health` | `backend/app/main.py` | Added `/health` alongside `/api/health` |
| No `.dockerignore` | `backend/` | Created |

### 🟢 GOOD — No change needed
| Item | Status |
|------|--------|
| CORS configurable via env var | ✅ Already correct |
| Database `create_all` is additive only | ✅ Safe |
| Seed script is idempotent | ✅ Checks before inserting |
| No destructive `drop_all` in app code | ✅ Confirmed by search |
| AI API key is server-side only | ✅ Never exposed to frontend |
| AI NoOp fallback when key missing | ✅ Graceful degradation |
| SQL injection protection via SQLAlchemy ORM | ✅ Parameterized queries |
| No hardcoded localhost in frontend src | ✅ Uses relative /api |
| asyncpg + psycopg2 drivers present | ✅ PostgreSQL ready |

---

## Hardcoded Secret Scan Results

| Pattern | Files Scanned | Result |
|---------|--------------|--------|
| `nvapi-` (NVIDIA key prefix) | All .py, .ts, .tsx, .js, .json, .ini, .yml | **Found in .env.example only — FIXED** |
| `localhost` in frontend src | All .ts, .tsx | None found |
| `PASSWORD` in application code | All .py | None found (only in .env.example placeholder) |

---

## API Routes Inventory

| Route | Method | Description |
|-------|--------|-------------|
| `/health` | GET | Health check (Render-compatible) |
| `/api/health` | GET | Health check (alternate) |
| `/api/organization` | GET | Demo org info |
| `/api/dashboard/summary` | GET | Revenue at risk summary |
| `/api/dashboard/leakage-breakdown` | GET | Leakage by category |
| `/api/dashboard/high-priority` | GET | Top priority issues |
| `/api/dashboard/recovery-pipeline` | GET | Recovery funnel |
| `/api/dashboard/recent-recoveries` | GET | Recent wins |
| `/api/dashboard/response-leakage` | GET | Response time analysis |
| `/api/leads` | GET | Lead list with pagination/search |
| `/api/leads/{id}` | GET | Lead detail + recovery score |
| `/api/leakage` | GET | Leakage events |
| `/api/leakage/{id}` | GET | Leakage event detail |
| `/api/leakage/{id}/status` | PATCH | Update leakage status |
| `/api/recommendations` | GET | AI recommendations |
| `/api/interventions` | GET/POST/PATCH | Intervention tracking |
| `/api/recovery` | GET/POST | Recovery outcomes |
| `/api/reports` | GET | Report generation |
| `/api/imports/upload` | POST | File upload |
| `/api/imports` | GET | Import history |
| `/api/imports/{id}` | GET | Import detail + preview |
| `/api/imports/{id}/suggest-mappings` | POST | AI column mapping |
| `/api/imports/{id}/confirm-mappings` | POST | Confirm column mappings |
| `/api/imports/{id}/process` | POST | Run import pipeline |

---

## Security Audit Summary

| Category | Status | Notes |
|----------|--------|-------|
| Secrets in code | ✅ Fixed | .env.example scrubbed |
| .gitignore coverage | ✅ Fixed | Root gitignore created |
| CORS | ✅ Configurable | Via CORS_ORIGINS env var |
| SQL injection | ✅ Safe | SQLAlchemy ORM throughout |
| XSS | ✅ React escapes by default | |
| CSRF | ℹ️ N/A (V1 no auth) | Session cookies not used |
| API key exposure | ✅ Server-side only | LLM keys never in JS bundle |
| Stack trace exposure | ✅ Fixed | Global exception handler |
| Docs endpoint in prod | ✅ Fixed | /docs disabled in production |
| Debug mode | ✅ Off | `APP_ENV` controls behavior |
| Non-root Docker user | ✅ Dockerfile | appuser created |
| Rate limiting | ⚠️ Not implemented | Consider adding for V2 |
| Authentication | ⚠️ V1 demo only | Multi-tenant auth deferred |
