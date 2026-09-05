# Revenue Leak Radar — Production Deployment Guide

**Architecture:** Vercel (frontend) + Render (backend) + PostgreSQL (database)

---

## 1. GitHub Setup

### Prepare repository
```bash
cd Revenue-Leakage-Deploy
git init
git add .
git commit -m "Initial commit — Revenue Leak Radar v1.0"
```

> **Before pushing**: verify `.env` is NOT staged:
> ```bash
> git status  # backend/.env should NOT appear
> ```

### Push to GitHub
```bash
git remote add origin https://github.com/YOUR_USERNAME/revenue-leak-radar.git
git branch -M main
git push -u origin main
```

---

## 2. Production Database Setup (Render PostgreSQL)

1. Go to [render.com](https://render.com) → **New → PostgreSQL**
2. Name: `revenue-radar-db`
3. Database: `revenue_radar`, User: `revenue_radar`
4. Plan: Starter (free) or Standard
5. Click **Create Database**
6. Copy **Internal Database URL** (use this for backend on Render)
   Format: `postgresql://revenue_radar:PASSWORD@HOST/revenue_radar`

Convert to async URL for `DATABASE_URL`:
```
postgresql+asyncpg://revenue_radar:PASSWORD@HOST/revenue_radar
```

---

## 3. Backend Deployment on Render

### Create Web Service
1. Render Dashboard → **New → Web Service**
2. Connect GitHub → select `revenue-leak-radar`
3. Configure:
   - **Name:** `revenue-radar-api`
   - **Root Directory:** `backend`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
   - **Plan:** Starter (free) or Standard

### Backend Environment Variables (set in Render Dashboard)
```
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST/revenue_radar
DATABASE_URL_SYNC=postgresql://USER:PASSWORD@HOST/revenue_radar
DEMO_ORG_ID=550e8400-e29b-41d4-a716-446655440000
UPLOAD_DIR=/tmp/uploads
CORS_ORIGINS=https://YOUR-APP.vercel.app
LLM_PROVIDER=noop
NVIDIA_API_KEY=
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
```

> **Note:** `PORT` is injected automatically by Render. Do not set it manually.

### Health Check (set in Render Dashboard)
- **Health Check Path:** `/health`
- Render will ping this every 30 seconds

---

## 4. Database Migration (run once after first deploy)

From the **Render Shell** (in your web service → Shell tab):
```bash
alembic upgrade head
```

Then seed demo data (optional, for demo/client presentation):
```bash
python -m scripts.seed_demo_data
```

---

## 5. Frontend Deployment on Vercel

### Deploy
1. Go to [vercel.com](https://vercel.com) → **New Project**
2. Import from GitHub → select `revenue-leak-radar`
3. Configure:
   - **Framework Preset:** Vite
   - **Root Directory:** `frontend`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
   - **Install Command:** `npm install`

### Frontend Environment Variables (set in Vercel Dashboard)
```
VITE_API_URL=https://revenue-radar-api.onrender.com/api
```

> Replace `revenue-radar-api` with your actual Render service name.

### SPA Routing
The `frontend/vercel.json` file handles client-side routing automatically — all routes redirect to `index.html`.

---

## 6. CORS Configuration

After deploying to Vercel, update the backend `CORS_ORIGINS` in Render:
```
CORS_ORIGINS=https://your-app-name.vercel.app
```

For custom domains:
```
CORS_ORIGINS=https://app.yourcompany.com,https://your-app-name.vercel.app
```

---

## 7. First Login / Admin Setup

Revenue Leak Radar V1 has no authentication. The app runs as a single demo organization ("GreenVista Realty Demo").

After seeding, navigate to your Vercel URL to see the dashboard.

---

## 8. AI Integration (Optional)

To enable NVIDIA NIM AI features (recommendation personalization, column mapping):

In Render environment variables:
```
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-YOUR-KEY-HERE
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
```

If `NVIDIA_API_KEY` is empty or invalid, the app gracefully falls back to the NoOp provider. **The app works correctly without AI.**

---

## 9. Deployment Verification

After deploying both services:

```bash
# 1. Test backend health
curl https://revenue-radar-api.onrender.com/health

# Expected: {"status":"healthy","service":"revenue-leak-radar","version":"1.0.0","env":"production"}

# 2. Test API
curl https://revenue-radar-api.onrender.com/api/dashboard/summary

# 3. Open frontend
open https://your-app.vercel.app
```

---

## 10. Local Development (unchanged)

```bash
# Backend
cd backend
.\venv\Scripts\activate   # Windows
# OR: source venv/bin/activate  # Mac/Linux
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm run dev

# App: http://localhost:5173
# API: http://localhost:8000
```

---

## 11. Commands Reference

| Task | Command | Directory |
|------|---------|-----------|
| Start backend (dev) | `uvicorn app.main:app --reload --port 8000` | `backend/` |
| Start backend (prod) | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` | `backend/` |
| Start frontend (dev) | `npm run dev` | `frontend/` |
| Build frontend (prod) | `npm run build` | `frontend/` |
| Run migrations | `alembic upgrade head` | `backend/` |
| Seed demo data | `python -m scripts.seed_demo_data` | `backend/` |
| Run backend tests | `pytest` | `backend/` |
| Install backend deps | `pip install -r requirements.txt` | `backend/` |
| Install frontend deps | `npm install` | `frontend/` |

---

## 12. Troubleshooting

### Backend 500 errors
- Check Render logs for error messages
- Verify `DATABASE_URL` is correct
- Run `alembic upgrade head` if schema is missing

### CORS errors in browser
- Verify `CORS_ORIGINS` in Render matches your exact Vercel URL
- Include `https://` — not just the domain

### Frontend shows "API Error"
- Verify `VITE_API_URL` in Vercel points to the correct Render URL
- Check the Render service is running (not spun down on free tier)

### Free tier cold starts
Render free tier spins down after inactivity. First request may take 30-60 seconds. Upgrade to Starter plan to avoid this.

### Migrations fail
```bash
# Check current migration state
alembic current

# If database is fresh, run from beginning
alembic upgrade head

# If specific migration failed, check which one
alembic history
```
