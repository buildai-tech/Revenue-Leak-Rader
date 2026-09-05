# Revenue Leak Radar

**Real-estate revenue intelligence platform** — detect and eliminate revenue leakage before it costs you deals.

---

## What It Does

Revenue Leak Radar monitors your CRM data and automatically detects:

- 🔴 **Dark Leads** — leads never contacted after 24+ hours
- 🔴 **No Follow-up** — leads with no activity after site visits
- 🟡 **SLA Violations** — response time breaches vs. your benchmark
- 🟡 **Negotiation Rot** — stalled negotiations past 14 days
- 🟡 **Inactive Rep Assignment** — leads assigned to reps who left
- 📊 **Revenue at Risk** — financial impact with confidence tiers
- 💡 **AI Recommendations** — personalized action playbooks per lead
- ✅ **Recovery Tracking** — track interventions and confirmed wins

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite 6 + TypeScript + TailwindCSS |
| Backend | FastAPI + Uvicorn (Python 3.11+) |
| Database | SQLite (dev) / PostgreSQL (production) |
| ORM | SQLAlchemy 2.0 async + Alembic |
| AI | NVIDIA NIM (optional) / NoOp fallback |

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- Node.js 20+
- npm 10+

### Backend
```bash
cd backend
python -m venv venv
.\venv\Scripts\activate       # Windows
# source venv/bin/activate    # Mac/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open: **http://localhost:5173**

The local `revenue_radar.db` SQLite database is pre-seeded with demo data.

---

## Environment Configuration

```bash
# Backend
cp backend/.env.example backend/.env
# Edit backend/.env with your values

# Frontend (optional for local dev)
cp frontend/.env.example frontend/.env.local
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full deployment instructions.

---

## Deployment

| Service | Platform |
|---------|---------|
| Frontend | Vercel |
| Backend | Render |
| Database | Render PostgreSQL / Supabase / Neon |

Full instructions: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Full deployment guide (Vercel + Render) |
| [docs/DATABASE_DEPLOYMENT.md](docs/DATABASE_DEPLOYMENT.md) | Database setup, migrations, seeding |
| [docs/DEPLOYMENT_AUDIT.md](docs/DEPLOYMENT_AUDIT.md) | Architecture audit and security findings |

---

## Key Commands

```bash
# Local development
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev

# Production build
cd frontend && npm run build

# Database migrations
cd backend && alembic upgrade head

# Seed demo data
cd backend && python -m scripts.seed_demo_data

# Run tests
cd backend && pytest
```

---

## Health Check

```
GET /health           → {"status": "healthy", "service": "revenue-leak-radar"}
GET /api/health       → same (alternate path)
```

---

## Project Structure

```
Revenue-Leakage-Deploy/
├── backend/
│   ├── app/
│   │   ├── ai/          # LLM provider, column mapper
│   │   ├── api/         # FastAPI routes (leads, leakage, dashboard...)
│   │   ├── core/        # Detection rules, financial engine
│   │   ├── models/      # SQLAlchemy ORM models
│   │   ├── schemas/     # Pydantic response schemas
│   │   ├── services/    # Business logic services
│   │   ├── config.py    # Settings (reads from .env)
│   │   ├── database.py  # SQLAlchemy engine + session
│   │   └── main.py      # FastAPI app + lifespan
│   ├── alembic/         # Database migrations
│   ├── scripts/         # seed_demo_data.py
│   ├── Dockerfile       # Production Docker image
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/  # Reusable UI components
│   │   ├── lib/         # API client, formatters
│   │   └── pages/       # Dashboard, Leads, Leakage, etc.
│   ├── vercel.json      # Vercel SPA routing + security headers
│   ├── vite.config.ts
│   └── .env.example
├── docs/                # Deployment documentation
├── docker-compose.yml   # Local PostgreSQL (optional)
└── .gitignore
```
