# CoachDB — Rival Coaches

Two AI soccer coaches compete in a seeded simulation and make halftime
decisions. See `PRD.md` for scope, `AGENTS.md` for agent contracts, and
`CHECKLIST.md` for who is working on what.

## Setup

```bash
# Backend (Python 3.12+)
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp ../.env.example .env            # then fill in values
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000/docs

# Frontend (Node 20+)
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

## Checks

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check .
cd frontend && npm run build
```

## Changing the contract

The shared contract is `backend/app/schemas/` plus `backend/app/api/`.
After any change to it:

```bash
cd backend && .venv/bin/python scripts/export_openapi.py   # updates openapi.json
cd frontend && npm run gen:api                             # updates src/api/schema.d.ts
```

Commit both generated files with the change and add a Handoff log entry
in `CHECKLIST.md`. A backend test fails if `openapi.json` is stale.

**Pitch coordinates:** 0–100 on both axes; x is left→right, y is
top→bottom goal line. The `top` team attacks toward y=100. See
`backend/app/schemas/frame.py`.
