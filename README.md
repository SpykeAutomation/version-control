# Spyke

Version control for Rockwell PLC projects (L5X) that shows changes as ladder
logic, not XML.

## The problem

PLC programs run critical equipment, but they're stored as large XML/binary
exports that ordinary diff tools can't read — a one-rung change looks like
thousands of altered lines. So most teams don't really version them. Instead:

- The PLC itself is the source of truth; the archived file may not match what's running.
- "Backups" are dated copies on a shared drive (`LineA_final_v2.ACD`).
- Change notes live in rung comments, when someone writes them.
- Fixes get made live and saved later, or never.

When something breaks, finding what changed means reading two exports side by side.

## What Spyke does

Commit an L5X file and Spyke stores it in a real Git repo, then diffs it in PLC
terms:

- **Semantic diffs** — added/removed/modified rungs, tags, routines, UDTs, and AOIs by name.
- **Visual ladder diffs** — changed rungs drawn as ladder logic.
- **Pull requests** — review and an enforced merge gate before a change ships; comments pin to a rung.
- **Branches, releases, history** — real Git underneath, so rollback is easy.

Docs, drawings, and configs are versioned alongside the program. Work in the web
app or the git-like `spyke` CLI.

## Self-host

Three parts, each with its own README: [`backend/`](backend/) (FastAPI · Git ·
SQLite), [`frontend/`](frontend/) (Vite · React), [`cli/`](cli/) (Go).

**Backend** — Docker on any Linux host with a domain pointed at it:

```bash
cd backend
cp .env.example .env      # set PLCVC_JWT_SECRET, DOMAIN, PLCVC_CORS_ORIGINS, PLCVC_HOST_DATA_DIR
docker compose up -d --build
```

TLS is automatic. Accounts are admin-created — bootstrap the first owner per
[`backend/README.md`](backend/README.md). Verify with `https://<DOMAIN>/health`.

**Frontend** — static Vite build:

```bash
cd frontend
npm install
# set VITE_API_URL=https://<your-backend> in .env.production
npm run build            # deploy dist/ with SPA fallback (serve index.html for all routes)
```

The serving origin must match the backend's `PLCVC_CORS_ORIGINS`.


