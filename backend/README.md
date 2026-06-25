# PLC Version Control

Semantic version control for Rockwell **L5X** PLC projects. Instead of diffing
XML text, it parses each project into a deterministic snapshot and shows changes
in PLC terms — added/removed/modified rungs, tags, routines, UDTs, and AOIs.

This repo is the **engine** plus a **HTTP API** that wraps it. The frontend is a
separate app that consumes the API documented below.

## How it works

```
L5X upload ─▶ parsers ─▶ deterministic snapshot (JSON) ─▶ commit to a Git repo
                                                                  │
                              ┌───────────────────────────────────┤
                  ChangeSet (whole-project semantic diff)   LadderDocument (drawable ladder diff)
                     → /diff  (the "code/text" panel)          → /diff/ladder (the "visual" panel)
```

- Each **project** is a real Git repo on disk, so branches, commits, history,
  and merges are plain Git.
- A diff is a pure function of two commits, so diff responses are **cached** by
  the commit pair and never go stale (`X-Cache: HIT|MISS` header).
- A small **SQLite** database holds what Git doesn't: accounts, project
  membership, pull requests, and comments.

## Run the backend locally

```bash
uv pip install -r requirements-app.txt --python .venv/bin/python   # or: pip install -r requirements-app.txt
cp .env.example .env
PLCVC_DATA_DIR=./data PLCVC_CORS_ORIGINS=http://localhost:5173 \
  .venv/bin/python -m uvicorn app.main:app --reload
```

- Interactive, try-it-live API docs: **http://localhost:8000/docs**
- Health check: **`GET /health`** → `{"status":"ok"}`
- End-to-end example of every call: [`scripts/smoke_api.py`](scripts/smoke_api.py)
  (`PLCVC_DATA_DIR=$(mktemp -d) .venv/bin/python scripts/smoke_api.py`)

---

# Frontend API contract

## Conventions

- **Base URL**: the backend origin (e.g. `http://localhost:8000` in dev).
- **Auth**: JWT Bearer. **Public registration is closed** — accounts are created
  by an admin (see "Creating accounts" below), so the frontend has **no signup
  form**. Get a token from `/auth/login`, then send `Authorization: Bearer
  <token>` on every other request.
- **Bodies**: JSON, **except** `/auth/login` (form-encoded) and
  `/projects/{id}/commits` (multipart file upload).
- **Errors**: `{"detail": "<message>"}` with status `400` (bad input / unknown
  ref / invalid L5X), `401` (missing/expired token), `403` (not a project member
  / registration closed), `404` (not found), `409` (conflict, e.g. duplicate
  email or merging a non-open PR), `422` (validation, e.g. malformed body), and
  `429` on `/auth/login` and the public `/invites/{token}` endpoints (too many
  attempts — back off, honor `Retry-After`).
- **CORS**: set `PLCVC_CORS_ORIGINS` to the frontend origin(s) (comma-separated),
  e.g. `https://app.spykeautomation.com`. Auth is header-based (no cookies).
- **Diff caching**: `GET` diff endpoints return an `X-Cache: HIT|MISS` header.

## Accounts & organizations

Public signup is removed from the app (and blocked at the Caddy edge as a second
layer). Accounts come from two places:

**1. Bootstrap a company + its owner** (admin, on the server). `create_user`
enforces the password policy (**≥12 chars with an upper- and lower-case letter
and a digit**):

```bash
docker compose exec api python -c "
from app.auth import create_org_with_owner
from app.db import SessionLocal
db = SessionLocal()
org, owner = create_org_with_owner(db, name='Acme Mfg',
    owner_email='owner@acme.com', owner_first='Owner', owner_last='Name',
    owner_password='ChangeMe1234')
print('org', org.id, 'owner', owner.id)
"
```

**2. The owner invites teammates** through the API (the `/orgs` + `/invites`
endpoints). A person joins an org **only** by accepting an owner's invitation —
never by naming one. Each invite is a one-time, expiring link
(`secrets.token_urlsafe`, stored only as a SHA-256 hash); accepting needs the
link **and** the invited email — a new email sets a password + name (account
created), an existing email is just linked. *(For the pilot the owner shares the
returned link directly; email delivery can be added later without other changes.)*

A plain user with no org: `create_user(db, email=..., first_name=...,
last_name=..., password=...)`.

## Endpoints

| Method | Path | Body / query | Returns |
|--------|------|--------------|---------|
| `POST` | `/auth/register` | _removed; accounts are admin-created (also `403` at the edge)_ | — |
| `POST` | `/auth/login` | form: `username`=email, `password` | `Token` (or `429` if rate-limited) |
| `GET`  | `/auth/me` | — | `User` |
| `POST` | `/orgs/{id}/invites` | `{email, role?}` (owner only) | `201` `Invite` (one-time link) |
| `GET`  | `/invites/{token}` | — (public, rate-limited) | `InvitePreview` (or `429`) |
| `POST` | `/invites/{token}/accept` | `{email, first_name?, last_name?, password?}` (public, rate-limited) | `AcceptResult` (or `429`) |
| `POST` | `/projects` | `{name}` | `201` `Project` |
| `GET`  | `/projects` | — | `[Project]` |
| `GET`  | `/projects/{id}` | — | `Project` |
| `GET`  | `/projects/{id}/members` | — | `[Member]` |
| `POST` | `/projects/{id}/members` | `{email, role?}` (owner only) | `201` `Member` |
| `GET`  | `/projects/{id}/branches` | — | `[string]` |
| `POST` | `/projects/{id}/branches` | `{name, start_point?="main"}` | `201` `[string]` |
| `POST` | `/projects/{id}/commits` | multipart: `file`, `branch`, `title`, `description?` | `201` `CommitResult` |
| `GET`  | `/projects/{id}/commits` | `?branch=main&limit=50` | `[Commit]` |
| `GET`  | `/projects/{id}/diff` | `?base=<ref>&head=<ref>` | `ChangeSet` |
| `GET`  | `/projects/{id}/diff/ladder` | `?base=<ref>&head=<ref>` | `LadderDocument` |
| `POST` | `/projects/{id}/pulls` | `{title, description?, source_branch, target_branch?="main"}` | `201` `Pull` |
| `GET`  | `/projects/{id}/pulls` | — | `[Pull]` |
| `GET`  | `/projects/{id}/pulls/{n}` | — | `Pull` |
| `GET`  | `/projects/{id}/pulls/{n}/diff` | — | `ChangeSet` |
| `GET`  | `/projects/{id}/pulls/{n}/diff/ladder` | — | `LadderDocument` |
| `POST` | `/projects/{id}/pulls/{n}/merge` | — | `MergeResult` |
| `GET`  | `/projects/{id}/pulls/{n}/comments` | — | `[Comment]` |
| `POST` | `/projects/{id}/pulls/{n}/comments` | `{body}` | `201` `Comment` |

`<ref>` is any Git ref: a branch name, a commit SHA, or an expression like `main~1`.

## Response shapes

```jsonc
Token   = { "access_token": string, "token_type": "bearer" }
Invite        = { "email": string, "role": string, "organization": string, "status": string,
                  "expires_at": datetime, "token": string, "accept_path": string }
InvitePreview = { "organization": string, "email": string, "role": string, "status": string }
AcceptResult  = { "status": "accepted", "access_token": string|null }
User    = { "id": int, "email": string, "first_name": string, "last_name": string,
            "organization": string|null }
Project = { "id": int, "name": string, "slug": string, "owner_id": int,
            "created_at": datetime, "branches": [string] }
Member  = { "id": int, "email": string, "first_name": string, "last_name": string,
            "role": "owner"|"member" }
CommitResult = { "sha": string, "branch": string, "title": string }
Commit  = { "sha": string, "title": string, "description": string,
            "author": string, "date": string /* ISO-8601 */ }
Pull    = { "number": int, "title": string, "description": string,
            "source_branch": string, "target_branch": string,
            "status": "open"|"merged"|"closed", "author": User,
            "merge_sha": string|null, "created_at": datetime }
MergeResult = { "status": "merged"|"conflict", "message": string,
                "merge_sha": string|null, "conflicts": [string] }
Comment = { "id": int, "author": User, "body": string, "created_at": datetime }
```

### `ChangeSet` — the whole-project semantic diff (the code/text panel)

Covers everything that changed: tags, UDTs, AOIs, modules, controller settings,
structured-text lines, and ladder rungs (as text).

```jsonc
ChangeSet = {
  "controller":          [FieldChange],
  "modules":             [EntityChange],
  "data_types":          [EntityChange],   // UDTs
  "add_on_instructions": [EntityChange],   // AOIs
  "controller_tags":     [EntityChange],
  "programs":            [ProgramChange],
  "tasks":               [EntityChange]
}
FieldChange   = { "path": string, "old": any, "new": any }          // missing side = null
EntityChange  = { "name": string, "kind": "added"|"removed"|"modified", "fields": [FieldChange] }
ProgramChange = { "name": string, "kind": ..., "fields": [FieldChange],
                  "tags": [EntityChange], "routines": [RoutineChange] }
RoutineChange = { "name": string, "kind": ..., "routine_type": "RLL"|"ST"|"FBD"|"SFC"|null,
                  "fields": [FieldChange], "rungs": [RungChange], "lines": [LineChange],
                  "formatting_only": bool, "note": string|null }
RungChange    = { "kind": "added"|"removed"|"modified"|"comment_changed",
                  "old_number": int|null, "new_number": int|null,
                  "old_text": string|null, "new_text": string|null,
                  "old_comment": string|null, "new_comment": string|null }
LineChange    = { "kind": "added"|"removed"|"modified", "old_number": int|null,
                  "new_number": int|null, "old_text": string|null, "new_text": string|null }
```

### `LadderDocument` — the drawable ladder diff (the visual panel)

One card per ladder routine that actually changed; the renderer only draws what
it's given (glyphs and operand labels are already resolved server-side).

```jsonc
LadderDocument = { "schema_version": int, "commit": string|null,
                   "routines": [RoutineLadderDiff] }
RoutineLadderDiff = { "controller": string|null, "program": string|null,
                      "routine": string|null, "routine_type": "RLL",
                      "old_label": string|null, "new_label": string|null,
                      "summary": RoutineSummary, "rungs": [RungDiff] }
RoutineSummary = { "rungs_modified": int, "rungs_added": int, "rungs_removed": int,
                   "additions": int, "removals": int }
RungDiff = { "status": "unchanged"|"added"|"removed"|"modified"|"comment_changed",
             "old_number": int|null, "new_number": int|null,
             "old_comment": string|null, "new_comment": string|null,
             "before": [Element], "after": [Element] }   // aligned row: draw `before` left, `after` right
Element  = { "kind": "contact"|"coil"|"box"|"branch"|"raw",
             "status": "unchanged"|"added"|"removed"|"modified",
             "form": string|null,        // contact: "no"|"nc"; coil: "ote"|"otl"|"otu"
             "label": string|null,       // contact/coil tag text
             "mnemonic": string|null,    // box: instruction or AOI name
             "operands": [Operand],      // box operands
             "legs": [[Element]],        // branch: parallel legs
             "text": string|null }       // raw: verbatim fallback
Operand  = { "label": string, "value": string, "changed": bool }  // `changed` tints one operand row
```

## Behaviors to handle in the UI

- **New project**: `branches` reports `["main"]`, but `main` has *no commits*
  until the first L5X upload. Create branches only after that first commit.
- **Two diff panels** for the same `base`/`head`: call `/diff` for the
  code/text + non-ladder changes, and `/diff/ladder` for the ladder diagrams.
- **Merge conflicts are not errors**: `POST .../merge` returns `200` with
  `{"status":"conflict", "message": "...", "conflicts": [files]}`. Show the
  message; the PR stays open to resolve. Success returns `{"status":"merged"}`.
- **Bad uploads** return `400` with a helpful `detail`, not a crash.

## Quick start (fetch)

```js
const API = "http://localhost:8000";
const { access_token } = await (await fetch(`${API}/auth/register`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, name, password }),
})).json();
const auth = { Authorization: `Bearer ${access_token}` };

const changeSet = await (await fetch(
  `${API}/projects/${id}/diff?base=main&head=feature/x`, { headers: auth }
)).json();
const ladder = await (await fetch(
  `${API}/projects/${id}/diff/ladder?base=main&head=feature/x`, { headers: auth }
)).json();
```

---

## Configuration

All settings are `PLCVC_*` environment variables — see [`.env.example`](.env.example):

| Variable | Purpose |
|----------|---------|
| `PLCVC_DATA_DIR` | Where Git repos + the SQLite DB live |
| `PLCVC_JWT_SECRET` | Signs JWTs — long random string |
| `PLCVC_JWT_EXPIRE_MINUTES` | Token lifetime (default 1 week) |
| `PLCVC_CORS_ORIGINS` | Allowed frontend origin(s), comma-separated, or `*` |
| `PLCVC_LOGIN_RATE_MAX` / `PLCVC_LOGIN_RATE_WINDOW_SECONDS` | Login attempts allowed per client IP per window (default 10 / 60s) |
| `PLCVC_INVITE_RATE_MAX` / `PLCVC_INVITE_RATE_WINDOW_SECONDS` | Invite preview/accept calls per client IP per window (default 20 / 60s) |
