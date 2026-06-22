# PLC Version Control

Semantic version control for Rockwell **L5X** PLC projects. Instead of diffing
XML text, it parses each project into a deterministic snapshot and shows changes
in PLC terms — added/removed/modified rungs, tags, routines, UDTs, and AOIs.

This repo contains the **engine** and a **HTTP API** that wraps it. A separate
frontend consumes the API.

## How it works

```
L5X upload ──▶ parsers ──▶ deterministic snapshot (JSON) ──▶ commit to a Git repo
                                                                      │
two refs ───────────────────────────────────────────▶ semantic diff (ChangeSet)
```

- Each **project** is a real Git repository on disk (`data/repos/<id>`), so
  branches, commits, history, and merges are plain Git.
- The **diff** is a structured `ChangeSet` (Pydantic) that serializes straight
  to JSON for the frontend.
- A small **SQLite** database holds what Git doesn't: user accounts, project
  membership, pull requests, and comments.

## Run locally

```bash
uv pip install -r requirements-app.txt --python .venv/bin/python   # or: pip install -r requirements-app.txt
cp .env.example .env                                                # optional
PLCVC_DATA_DIR=./data .venv/bin/python -m uvicorn app.main:app --reload
```

Open the interactive API docs at **http://localhost:8000/docs** (your frontend
partner can explore and try every endpoint there). Health check: `/health`.

Run the end-to-end smoke test:

```bash
PLCVC_DATA_DIR=$(mktemp -d) .venv/bin/python scripts/smoke_api.py
```

## API surface

Auth is JWT Bearer. Register or log in, then send `Authorization: Bearer <token>`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/auth/register` | Create account → returns token |
| `POST` | `/auth/login` | Log in (form: `username`=email, `password`) → token |
| `GET`  | `/auth/me` | Current user |
| `POST` | `/projects` | Create a project (inits a Git repo with `main`) |
| `GET`  | `/projects` | List my projects |
| `GET`  | `/projects/{id}` | Project details + branches |
| `GET`/`POST` | `/projects/{id}/members` | List / add a member by email (owner only) |
| `GET`/`POST` | `/projects/{id}/branches` | List / create branches |
| `POST` | `/projects/{id}/commits` | Upload an L5X (multipart: `file`, `branch`, `title`, `description`) |
| `GET`  | `/projects/{id}/commits?branch=` | Commit history |
| `GET`  | `/projects/{id}/diff?base=&head=` | **Semantic diff** between two refs → `ChangeSet` |
| `POST` | `/projects/{id}/pulls` | Open a pull request |
| `GET`  | `/projects/{id}/pulls` | List pull requests |
| `GET`  | `/projects/{id}/pulls/{n}` | PR details |
| `GET`  | `/projects/{id}/pulls/{n}/diff` | PR diff (target → source) → `ChangeSet` |
| `POST` | `/projects/{id}/pulls/{n}/merge` | Merge; returns `{status: "merged"}` or `{status: "conflict", message, conflicts[]}` |
| `GET`/`POST` | `/projects/{id}/pulls/{n}/comments` | List / add comments |

## Configuration

All via `PLCVC_*` environment variables — see [`.env.example`](.env.example).
The only ones that matter in production: `PLCVC_DATA_DIR` (persistent path),
`PLCVC_JWT_SECRET` (long random string), `PLCVC_CORS_ORIGINS` (your frontend URL).

## Deploy

The service stores Git repos + SQLite on the filesystem, so it needs a
**persistent disk**. A universal [`Dockerfile`](Dockerfile) is provided.

### Render (recommended — push-to-deploy, managed HTTPS)

1. Push this repo to GitHub.
2. In the Render dashboard: **New ▸ Blueprint**, pick this repo. It reads
   [`render.yaml`](render.yaml): a Docker web service on the Starter plan with a
   1 GB persistent disk mounted at `/data` and a generated `PLCVC_JWT_SECRET`.
3. Click **Apply**. You get a public `https://<name>.onrender.com` URL.
4. Set `PLCVC_CORS_ORIGINS` to your frontend's URL once it's deployed.

### DigitalOcean droplet (uses your $200 Student Pack credit)

1. Create an Ubuntu droplet, install Docker + the Compose plugin.
2. `git clone` this repo, then:
   ```bash
   export PLCVC_JWT_SECRET=$(openssl rand -hex 32)
   docker compose up -d --build
   ```
   Data persists in the `plc-data` volume (see [`docker-compose.yml`](docker-compose.yml)).
3. Put Caddy or nginx in front for automatic HTTPS on your domain.

## Notes for scaling past the pilot

- Runs as a **single web worker**: Git operations on a project share a working
  tree and are serialized by an in-process lock (`app/storage.py`). To run
  multiple workers/replicas later, move that lock to the DB (advisory locks) or
  switch to a bare-repo-per-operation model.
- SQLite is fine for a pilot; swap `PLCVC_*` `db_url` for Postgres when needed.
- Schema is created on startup; add Alembic migrations before the schema needs
  to change without data loss.
