# PLC Version Control

Semantic version control for Rockwell **L5X** PLC projects. Instead of diffing
XML text, it parses each project into a deterministic snapshot and shows changes
in PLC terms — added/removed/modified rungs, tags, routines, UDTs, and AOIs.

This repo is the **engine** plus a **HTTP API** that wraps it. The frontend is a
separate app that consumes the API documented below.

## How it works

```
files upload ─▶ L5X parsed to a deterministic snapshot (JSON); other files kept as-is
                                       └─▶ one commit to the project's Git repo
                                                                  │
                              ┌───────────────────────────────────┤
                  per-file ChangeSet (semantic diff)        per-file LadderDocument (drawable)
                     → /diff/changeset (code/text panel)       → /diff/ladder (visual panel)
        ( /diff returns the manifest of which files changed; drill in per file )
```

- A **project holds many files**: any number of L5X files (each parsed and
  snapshotted, with the raw upload kept for exact download) plus arbitrary
  non-L5X files (stored verbatim). One upload = one commit of 1..N files.
- Each **project** is a real Git repo on disk, so branches, commits, history,
  and merges are plain Git.
- A diff is a pure function of two commits, so diff responses are **cached** by
  the commit pair and never go stale (`X-Cache: HIT|MISS` header).
- A small **SQLite** database holds what Git doesn't: accounts, project
  membership, pull requests, and comments.
- Access is **per-project** (owner / admin / member). Deleting a project
  cascades to its members, pull requests, comments, repo, and cached diffs.
  Each **organization** has a storage quota counting the logical bytes of its
  committed uploads (deleting a project gives its bytes back).

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
  `/projects/{id}/commits` (multipart; one or more `files` parts + form fields).
- **Errors**: `{"detail": "<message>"}` with status `400` (bad input / unknown
  ref / invalid L5X), `401` (missing/expired token), `403` (not a project member
  / registration closed), `404` (not found), `409` (conflict, e.g. duplicate
  email or merging a non-open PR), `413` (an uploaded file exceeds the per-file
  size limit), `507` (the organization's storage quota is full),
  `422` (validation, e.g. malformed body), and `429` on
  `/auth/login` and the public `/invites/{token}` endpoints (too many attempts —
  back off, honor `Retry-After`).
- **CORS**: set `PLCVC_CORS_ORIGINS` to the frontend origin(s) (comma-separated),
  e.g. `https://app.spykeautomation.com`. Auth is header-based (no cookies).
- **Diff caching**: `GET` diff endpoints return an `X-Cache: HIT|MISS` header.
- **Pagination**: list endpoints that can grow (`commits`, `pulls`, `comments`,
  `tags`, `activity`, `orgs/{id}/users`) take `?limit=&offset=` and return the
  full count in an **`X-Total-Count`** response header — render pagers from that.
  Other lists (branches, members) are inherently small and aren't paged.

## Accounts & organizations

Public signup is removed from the app (and blocked at the reverse proxy as a
second layer). Accounts come from two places:

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

## Roles & permissions

Roles are **per project** — a member's role on one project says nothing about
another. The creator is the `owner`; the owner and any `admin` are "managers".

| Capability | owner | admin | member |
|-----------|:---:|:---:|:---:|
| View, upload commits, comment/reply, open PRs, approve/request-changes, resolve, cut tags, delete branches | ✅ | ✅ | ✅ |
| Merge a PR (subject to the target branch's required approvals) | ✅ | ✅ | ✅ |
| Edit/delete **your own** comment; edit any PR; delete your **own** open PR | ✅ | ✅ | ✅ |
| Manage a PR's reviewers; delete **any** open PR; delete **any** comment | ✅ | ✅ | author only |
| Add members, change roles, rename, edit settings, **protect branches**, delete tags, **delete the project** | ✅ | ✅ | ❌ |
| Remove or demote an **admin** | ✅ | ❌ | ❌ |

Members can merge — the gate is the **target branch's `required_approvals`**, not
the role. The owner can't be removed or demoted. A manager-only call by a plain
member returns `403`; `GET /projects/{id}` echoes the caller's role as
`your_role`, so
the UI can hide controls the user isn't allowed to use.

## CLI sessions & account lifecycle

**Browser (device) login.** The CLI signs in with the OAuth 2.0 device grant
(RFC 8628): `POST /auth/device/code` returns a long `device_code` (the CLI polls
with it) plus a short `user_code` the user approves at the web app's `/cli-auth`
page. Hardening:
- Both codes come from a CSPRNG; only the `device_code`'s SHA-256 hash is stored.
  `/code`, `/info`, `/approve`, and `/token` are all rate-limited per IP.
- `/code` records the CLI's context — an optional `client_name` from the CLI plus
  the server-observed IP and user-agent. The approval page first calls
  `GET /auth/device/info?user_code=` so it can show *"approving a sign-in from
  &lt;ip&gt; · &lt;client&gt;"* before the user confirms — the human defence
  against a relayed or phished code.
- The token is released only to the approved `device_code`, never returned from
  `/approve`.

**CLI tokens are session-backed and revocable.** Unlike the one-week web-login
JWT, a CLI token lasts **180 days** and carries a session id (`sid`). Each
approved login is a session row; `GET /auth/me/sessions` lists them (with
`last_used_at`, and the current session flagged) and `DELETE /auth/me/sessions/{id}`
revokes one — the token stops working on its next request.

**Removing people & deleting accounts** (org owner, under `/orgs`):
- `DELETE /orgs/{id}/members/{user_id}` un-maps someone from the org; their
  account and authored history stay.
- `DELETE /orgs/{id}/accounts/{user_id}` **soft-deletes** the account: access is
  cut everywhere (login and every request rejected, org + project memberships
  removed, CLI sessions revoked), but the user row is **kept** so their commits,
  PRs, and comments remain — `User.deleted` is set so the frontend can grey the
  name out. Any project the deleted user **owned** is reassigned to the org owner
  so it isn't orphaned.
- Project-level removal stays `DELETE /projects/{id}/members/{user_id}`
  (owner/admin).

**Ownership transfer.** `POST /projects/{id}/transfer` (current project owner)
hands a project to another user — they get the `owner` role and the previous
owner is demoted to `admin` (keeps access). Account deletion reuses the same
logic to reassign owned projects to the org owner.

**Audit.** CLI approvals/revocations, member removals, and account deletions are
written to an account-level audit log (`app/audit.py` → the `audit_log` table),
separate from the per-project activity feed.

## Endpoints

| Method | Path | Body / query | Returns |
|--------|------|--------------|---------|
| `POST` | `/auth/register` | _removed; accounts are admin-created (also `403` at the edge)_ | — |
| `POST` | `/auth/login` | form: `username`=email, `password` | `Token` (or `429` if rate-limited) |
| `GET`  | `/auth/me` | — | `User` |
| `PATCH` | `/auth/me` | `{first_name?, last_name?, avatar?}` | `User` (`avatar` = 3 alphanumerics) |
| `POST` | `/auth/me/password` | `{current_password, new_password}` | `204`; `403` wrong current, `422` weak new |
| `GET`  | `/auth/me/sessions` | — | `[CliSession]` — your active CLI logins, newest first |
| `DELETE` | `/auth/me/sessions/{id}` | — | `204` — revoke one of your CLI logins (idempotent; `404` if not yours) |
| `POST` | `/auth/device/code` | `{client_name?}` (public, rate-limited) | `DeviceCode` — starts the CLI device-login flow; records the client label + server-side IP/user-agent |
| `GET`  | `/auth/device/info` | `?user_code=` (authenticated, rate-limited) | `DeviceInfo` — the pending request's context for the approval page; `400` invalid/expired, `409` already approved |
| `POST` | `/auth/device/approve` | `{user_code}` (authenticated, rate-limited) | `200` `{status:"approved"}`; `400` invalid/expired, `409` already approved, `401` not signed in |
| `POST` | `/auth/device/token` | `{device_code}` (public, rate-limited) | `Token` (a **180-day, revocable CLI token**) once approved; else `400` with `detail` = `authorization_pending` / `expired_token` |
| `POST` | `/orgs/{id}/invites` | `{email, role?}` (owner only) | `201` `Invite` (one-time link) |
| `GET`  | `/orgs/{id}/users` | `?limit=50&offset=0` (org members) | `[User]` + `X-Total-Count` |
| `DELETE` | `/orgs/{id}/members/{user_id}` | — (org owner) | `204` — remove from the org (account kept); `400` on the owner, `404` if not a member |
| `DELETE` | `/orgs/{id}/accounts/{user_id}` | — (org owner) | `204` — soft-delete the account (access cut, history kept); `409` if already deleted |
| `GET`  | `/invites/{token}` | — (public, rate-limited) | `InvitePreview` (or `429`) |
| `POST` | `/invites/{token}/accept` | `{email, first_name?, last_name?, password?}` (public, rate-limited) | `AcceptResult` (or `429`) |
| `POST` | `/projects` | `{name, description?}` | `201` `Project` |
| `GET`  | `/projects` | — | `[Project]` |
| `GET`  | `/projects/{id}` | — | `Project` |
| `PATCH` | `/projects/{id}` | `{name?, description?}` (owner/admin) | `Project` |
| `DELETE` | `/projects/{id}` | — (owner/admin) | `204` — deletes the repo, members, PRs (+ their reviewers/approvals/comments), branch protections, activity & cached diffs |
| `GET`  | `/projects/{id}/overview` | `?ref=main` | `RepositoryOverview` |
| `GET`  | `/projects/{id}/members` | — | `[Member]` |
| `POST` | `/projects/{id}/members` | `{email, role?}` — `role` ∈ `member`\|`admin` (owner/admin) | `201` `Member` |
| `PATCH` | `/projects/{id}/members/{user_id}` | `{role}` ∈ `member`\|`admin` (owner/admin) | `Member` |
| `DELETE` | `/projects/{id}/members/{user_id}` | — (owner/admin; only the owner may remove an admin) | `204` |
| `POST` | `/projects/{id}/transfer` | `{new_owner_id}` (current owner) | `Member` (the new owner) — previous owner demoted to `admin`; `404` unknown/deleted user, `400` already the owner |
| `GET`  | `/projects/{id}/branches` | — | `[Branch]` (enriched: tip commit, default/protected, ahead/behind, merged) |
| `POST` | `/projects/{id}/branches` | `{name, start_point?="main"}` | `201` `[Branch]` |
| `DELETE` | `/projects/{id}/branches/{branch}` | — (any member) | `204`; `400` if it's the default or a protected branch |
| `PUT` | `/projects/{id}/branches/{branch}/protection` | `{protected, required_approvals?=0}` (owner/admin) | `Branch`; `400` unprotecting the default branch |
| `POST` | `/projects/{id}/commits` | multipart: `files` (one or more, ≤100 MB each), `branch`, `title`, `description?` | `201` `CommitResult` (or `413` if a file is too big) |
| `GET`  | `/projects/{id}/commits` | `?branch=main&limit=50&offset=0` | `[Commit]` + `X-Total-Count` (each tagged with `branch` + `files_changed`) |
| `GET`  | `/projects/{id}/commits/{sha}` | — | `CommitDetail` (the commit + files it changed vs its parent) |
| `GET`  | `/projects/{id}/commits/{sha}/diff/changeset` | `?path=l5x/<name>` | `ChangeSet` (parent → commit) |
| `GET`  | `/projects/{id}/commits/{sha}/diff/ladder` | `?path=l5x/<name>` | `LadderDocument` (parent → commit) |
| `GET`  | `/projects/{id}/commits/{sha}/diff/text` | `?path=files/<nested/path>` | `TextDiff` (parent → commit) |
| `GET`  | `/projects/{id}/commits/{sha}/tree` | `?path=l5x/<name>` | `ProjectTree` (organizer of one L5X at the commit, vs its parent) |
| `GET`  | `/projects/{id}/commits/{sha}/routine` | `?program=<name>&routine=<name>&path=l5x/<name>` (`path` optional; without it every L5X at the commit is probed) | `RoutineFull` — the routine's full content at the commit, not a diff; `404` for encoded (source-protected) routines and FBD/SFC |
| `GET`  | `/projects/{id}/compare` | `?base=<ref>&head=<ref>` | `CompareView` (rolled-up summary + impact rows) |
| `GET`  | `/projects/{id}/tags` | `?limit=50&offset=0` | `[Tag]` + `X-Total-Count` (newest first; tags = releases) |
| `POST` | `/projects/{id}/tags` | `{name, ref?="main", message?}` (any member) | `201` `Tag` |
| `DELETE` | `/projects/{id}/tags/{name}` | — (owner/admin) | `204` |
| `GET`  | `/projects/{id}/activity` | `?limit=50&offset=0` | `[Activity]` + `X-Total-Count` (newest first) |
| `GET`  | `/projects/{id}/files` | `?ref=main` | `FileListing` |
| `GET`  | `/projects/{id}/files/raw` | `?ref=<ref>&path=<repo-path>` | raw bytes (file download) |
| `GET`  | `/projects/{id}/diff` | `?base=<ref>&head=<ref>` | `DiffManifest` (changed files) |
| `GET`  | `/projects/{id}/diff/changeset` | `?base=<ref>&head=<ref>&path=l5x/<name>` | `ChangeSet` |
| `GET`  | `/projects/{id}/diff/ladder` | `?base=<ref>&head=<ref>&path=l5x/<name>` | `LadderDocument` |
| `GET`  | `/projects/{id}/diff/text` | `?base=<ref>&head=<ref>&path=files/<nested/path>` | `TextDiff` |
| `GET`  | `/projects/{id}/tree` | `?base=<ref>&head=<ref>&path=l5x/<name>` | `ProjectTree` (organizer of one L5X at `head`, tagged by the `base..head` diff) |
| `GET`  | `/projects/{id}/l5x` | `?ref=<ref>&path=l5x/<name>&section=controller\|datatypes\|tags\|modules\|aoi` (`section=aoi` also needs `&name=<aoi>`) | `L5XSection` — one raw section of the parsed file at `ref`, for the organizer's detail tables; cached per commit |
| `POST` | `/projects/{id}/pulls` | `{title, description?, source_branch, target_branch?="main"}` | `201` `Pull` |
| `GET`  | `/projects/{id}/pulls` | `?status_filter=open&limit=50&offset=0` | `[Pull]` + `X-Total-Count` |
| `GET`  | `/projects/{id}/pulls/{n}` | — | `Pull` |
| `PATCH` | `/projects/{id}/pulls/{n}` | `{title?, description?}` (any member) | `Pull` |
| `DELETE` | `/projects/{id}/pulls/{n}` | — (author/manager; **open only**) | `204`; `409` if not open |
| `POST` | `/projects/{id}/pulls/{n}/reviewers` | `{email}` (author/manager) | `201` `Pull` |
| `DELETE` | `/projects/{id}/pulls/{n}/reviewers/{user_id}` | — (author/manager) | `204` |
| `POST` | `/projects/{id}/pulls/{n}/approve` | — (any member) | `Pull` |
| `POST` | `/projects/{id}/pulls/{n}/request-changes` | — (any member) | `Pull` |
| `DELETE` | `/projects/{id}/pulls/{n}/review` | — (withdraw your own verdict) | `204` |
| `GET`  | `/projects/{id}/pulls/{n}/mergeability` | — | `Mergeability` (conflict dry-run + approval gate) |
| `GET`  | `/projects/{id}/pulls/{n}/diff` | — | `DiffManifest` (changed files) |
| `GET`  | `/projects/{id}/pulls/{n}/diff/changeset` | `?path=l5x/<name>` | `ChangeSet` |
| `GET`  | `/projects/{id}/pulls/{n}/diff/ladder` | `?path=l5x/<name>` | `LadderDocument` |
| `GET`  | `/projects/{id}/pulls/{n}/diff/text` | `?path=files/<nested/path>` | `TextDiff` |
| `POST` | `/projects/{id}/pulls/{n}/merge` | — | `MergeResult`; `409` if not open or below required approvals |
| `GET`  | `/projects/{id}/pulls/{n}/comments` | `?limit=100&offset=0` | `[Comment]` + `X-Total-Count` (flat; nest by `parent_id`) |
| `POST` | `/projects/{id}/pulls/{n}/comments` | `{body, parent_id?, anchor?}` | `201` `Comment` |
| `PATCH` | `/projects/{id}/pulls/{n}/comments/{cid}` | `{body?, resolved?}` (body = author only) | `Comment` |
| `DELETE` | `/projects/{id}/pulls/{n}/comments/{cid}` | — (author/manager) | `204` |
| `GET`  | `/storage` | — | `StorageUsage` — the caller's org usage vs. its quota |

`<ref>` is any Git ref: a branch name, a commit SHA, or an expression like `main~1`.

`<repo-path>` and the `path` query come straight from a manifest entry's `path`:
`l5x/<name>` for an L5X file (use it with `/diff/changeset` and `/diff/ladder`),
or `files/<nested/path>` for any other file (use it with `/diff/text`). To download a
file's exact bytes at a ref, pass its repo path to `/files/raw` — for an
original L5X that is `l5x/<name>/source.L5X`.

## Response shapes

```jsonc
Token   = { "access_token": string, "token_type": "bearer" }
DeviceCode = { "device_code": string,   // the CLI polls /auth/device/token with this
               "user_code": string,      // short code the user approves in the web app
               "verification_uri": string,          // the web app's /cli-auth page
               "verification_uri_complete": string, // same URL with ?code= prefilled
               "interval": int,           // seconds between token polls
               "expires_in": int }        // seconds until the codes expire
DeviceInfo = { "user_code": string, "client_name": string|null, "client_ip": string|null,
               "requested_at": datetime, "expires_in": int }  // context for the /cli-auth approval page
CliSession = { "id": int, "client_name": string|null, "client_ip": string|null,
               "created_at": datetime,            // when the CLI logged in
               "last_used_at": datetime|null, "expires_at": datetime,
               "current": bool }                  // the session making this request
Invite        = { "email": string, "role": string, "organization": string, "status": string,
                  "expires_at": datetime, "token": string, "accept_path": string }
InvitePreview = { "organization": string, "email": string, "role": string, "status": string }
AcceptResult  = { "status": "accepted", "access_token": string|null }
User    = { "id": int, "email": string, "first_name": string, "last_name": string,
            "organization": string|null, "avatar": string,  // avatar = 3-char code; frontend renders it
            "deleted": bool }  // soft-deleted account — grey it out
Project = { "id": int, "name": string, "slug": string, "description": string,
            "owner": User, "your_role": "owner"|"admin"|"member"|null,
            "created_at": datetime, "branches": [string] }
Member  = { "id": int, "email": string, "first_name": string, "last_name": string,
            "role": "owner"|"admin"|"member" }
RepositoryOverview = { "id": int, "name": string, "description": string,
                       "default_branch": string, "file_count": int, "l5x_count": int,
                       "open_pull_count": int, "unresolved_comment_count": int,
                       "controller_name": string|null,  // from the latest commit's L5X
                       "processor_type": string|null,    // the controller "model"
                       "firmware": string|null,          // "major.minor"
                       "latest_commit": Commit|null,
                       "latest_release": Tag|null }       // newest tag, for "Latest release"
StorageUsage = { "used_bytes": int, "limit_bytes": int, "project_count": int }
CommitResult = { "sha": string, "branch": string, "title": string }
Commit  = { "sha": string, "title": string, "description": string,
            "author": string, "date": string /* ISO-8601 */,  // author = the uploading user
            "branch": string|null,        // the branch it was listed under (when known)
            "files_changed": int }        // logical files changed vs its first parent
Branch  = { "name": string, "is_default": bool, "is_protected": bool,
            "required_approvals": int,     // approvals a PR into this branch needs to merge
            "latest_commit": Commit|null,  // null on an unborn branch (no commits yet)
            "ahead": int, "behind": int,   // vs the default branch (main)
            "merged": bool }               // fully merged into the default branch (ahead == 0)
CommitDetail = { "sha": string, "title": string, "description": string,
                 "author": string, "date": string, "branch": string|null,
                 "parent": string|null,        // first-parent SHA; null for the root commit
                 "files_changed": int,
                 "files": [ChangedFile] }      // same manifest shape as /diff
Tag     = { "name": string, "sha": string,     // sha = the commit the tag points to
            "message": string,                 // release notes (empty for a lightweight tag)
            "tagger": string, "date": string,  // who cut it + ISO-8601 tag date
            "annotated": bool, "commit": Commit|null }  // the tagged commit's summary
FileListing = { "files": [FileEntry] }
FileEntry   = { "path": string, "kind": "l5x"|"file",     // "l5x/<name>" or "files/<nested/path>"
                "size": int,                               // bytes; for an L5X, its source.L5X size
                "modified_by": string, "modified_at": string }  // last commit's author + ISO-8601 date
DiffManifest = { "files": [ChangedFile] }
ProjectTree = { "schema_version": int, "root": TreeNode }   // per-L5X organizer, nested under the file tree
                // schema_version 3 adds: Data Types subfolders (User-Defined / Strings /
                // Add-On-Defined AOI refs, keys "datatype:aoi:<name>"), AOI routine children
                // (keys "aoi:<a>/routine:<r>", NO ladder-card identity), a Motion Groups
                // folder ("motion:<group>" / "motion:<group>/axis:<tag>"; motion tags also
                // stay under Controller Tags), Power-Up / Controller Fault Handler folders,
                // and task program refs carrying the routine subtree
                // ("task:<t>/program:<p>/routine:<r>", WITH ladder-card identity). The flat
                // Programs folder and its keys are unchanged.
TreeNode    = { "key": string, "label": string,
                "kind": "controller"|"folder"|"program"|"routine"|"aoi"|"datatype"|"tag"|"module"|"task",
                "status": "unchanged"|"added"|"removed"|"modified",  // the node's own change
                "descendant_changed": bool,                          // something beneath it changed
                "routine_type": string|null,                         // routine nodes only
                "controller": string|null, "program": string|null, "routine": string|null,  // ladder-card identity
                "children": [TreeNode] }
ChangedFile  = { "path": string, "kind": "l5x"|"file",
                 "change": "added"|"modified"|"removed",
                 "views": [string] }   // drill-down views: l5x→["changeset","ladder"], file→["text"]
TextDiff = { "path": string, "binary": bool, "unified": string|null }  // null when binary
Pull    = { "number": int, "title": string, "description": string,
            "source_branch": string, "target_branch": string,
            "status": "open"|"merged"|"closed", "author": User,
            "merge_sha": string|null, "created_at": datetime, "updated_at": datetime,
            "reviewers": [User],                       // invited approvers
            "reviews": [Review],                       // verdicts cast so far
            "required_approvals": int,                 // from the target branch's protection
            "approvals": int, "approved": bool }       // count + (approvals >= required)
Review  = { "user": User, "state": "approved"|"changes_requested", "created_at": datetime }
Mergeability = { "mergeable": bool, "conflicts": [string],   // conflict dry-run (lock-free)
                 "approvals": int, "required_approvals": int, "approved": bool,
                 "can_merge": bool }   // open && mergeable && approved — gate the merge button on this
MergeResult = { "status": "merged"|"conflict", "message": string,
                "merge_sha": string|null, "conflicts": [string] }
Comment = { "id": int, "author": User, "body": string, "resolved": bool,
            "parent_id": int|null,        // null = top-level; else the comment it replies to
            "anchor": CommentAnchor|null, // set for a change-level comment, null for PR-level
            "created_at": datetime, "edited_at": datetime|null }
CommentAnchor = { "path": string|null,    // "l5x/<name>" or "files/<path>"
                  "routine": string|null, "rung": int|null, "sha": string|null }
CompareView = { "base": string, "head": string, "summary": CompareSummary,
                "files": [CompareRow], "affected_symbols": [string] }  // de-duped across files
CompareSummary = { "commits": int, "files_changed": int, "l5x_changed": int,
                   "rungs_added": int, "rungs_removed": int, "rungs_modified": int,
                   "routines_modified": int, "tags_impacted": int }
CompareRow = { "path": string, "kind": "l5x"|"file", "change": "added"|"modified"|"removed",
               "rungs_added": int, "rungs_removed": int, "rungs_modified": int,
               "symbols": [string], "views": [string] }
Activity = { "id": int, "actor": User|null,  // null if the actor was since deleted
             "verb": string,                 // "pull.merged", "comment.added", "branch.created", …
             "target_type": string, "target_id": string, "summary": string, "created_at": datetime }
```

### `ChangeSet` — one L5X file's semantic diff (the code/text panel)

Returned by `/diff/changeset?path=l5x/<name>` for a single L5X file. Covers
everything that changed in it: tags, UDTs, AOIs, modules, controller settings,
structured-text lines, and ladder rungs (as text). A file that was added or
removed diffs against an empty document, so its contents show entirely as
added/removed.

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

### `LadderDocument` — one L5X file's drawable ladder diff (the visual panel)

Returned by `/diff/ladder?path=l5x/<name>`. One card per ladder routine that
actually changed; the renderer only draws what it's given (glyphs and operand
labels are already resolved server-side).

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

### `RoutineFull` — one routine's full content at a commit (the Files tab)

Returned by `/commits/{sha}/routine?program=<name>&routine=<name>`. Not a
diff: the whole routine as committed, read straight from the snapshot. A
discriminated union on `kind`:

```jsonc
RoutineFull       = RoutineFullLadder | RoutineFullCode
RoutineFullLadder = { "kind": "ladder",
                      "ladder": RoutineLadderDiff }  // same card shape as LadderDocument:
                                                     // every rung "unchanged", `before` empty,
                                                     // the content drawn in `after`;
                                                     // new_label = short commit sha
RoutineFullCode   = { "kind": "structured",
                      "ref": string,                             // short commit label, e.g. "a7f3c9d"
                      "lines": [{ "ln": int, "text": string }] } // 1-based line numbers
```

### `L5XSection` — raw sections of one L5X file (organizer detail tables)

Returned by `/l5x?ref=&path=l5x/<name>&section=`. The data behind the
organizer's detail views: UDT members, AOI parameters/routines, the
controller-tag grid, the I/O module table, controller properties. Everything
is serialized straight from the parsed snapshot (the same field names the
parser models use); responses are cached per commit like every diff view.

```jsonc
L5XSection = { "schema_version": 1, "section": string, "data": ... }
// data by section:
//   controller  -> Controller object (name, processor_type, revs, safety/redundancy blocks, ...)
//   datatypes   -> [DataType] incl. members (name, data_type, dimension, radix, hidden, ...)
//   tags        -> [Tag] controller tags WITHOUT the heavy per-tag blobs:
//                  `values`, `comments`, `message_config` are excluded
//                  (measured 1.36 MB -> 91 KB on a real export); scalar `value` stays
//   modules     -> [Module] WITHOUT `config_values`, `connections`,
//                  `rack_connections`, `extended_properties` (78 -> 28 KB)
//   aoi         -> ONE full AOI (parameters, local_tags, routines with content);
//                  requires &name=<aoi>. The whole AOI list is deliberately not
//                  offered (812 KB+ raw); fetch per AOI (~13 KB) on click.
```

Errors: unknown `section` → `422`; `section=aoi` without `name` → `400`;
no such L5X file / AOI at the ref, or a bad ref → `400`.

## Behaviors to handle in the UI

- **New project**: `branches` reports `["main"]`, but `main` has *no commits*
  until the first upload (`GET /files` is empty too). Create branches only after
  that first commit.
- **Diff is per file, reached from the manifest**: call `/diff?base=&head=` for
  the list of changed files. For each L5X file, render its two panels from
  `/diff/changeset?path=…` (code/text) and `/diff/ladder?path=…` (ladder); for a
  non-L5X file, call `/diff/text?path=…` (a `null` `unified` means it's binary —
  show "binary changed" and offer a download via `/files/raw`).
- **Merge conflicts are not errors**: `POST .../merge` returns `200` with
  `{"status":"conflict", "message": "...", "conflicts": [files]}`. Show the
  message; the PR stays open to resolve. Success returns `{"status":"merged"}`.
- **Bad uploads** return `400` with a helpful `detail`, not a crash. Uploads are
  **atomic** — one bad file (or two files mapping to the same path) rejects the
  whole batch, nothing is committed.
- **Uploading folders (nested paths)**: non-L5X files keep their folder layout
  under `files/`. To preserve it, send each file's *relative path* as its
  multipart `filename` (e.g. `docs/specs/io.csv`), not just the basename — from a
  folder picker use `file.webkitRelativePath`. Every part is still named `files`.
  Unsafe paths (`..`, absolute, reserved Windows names, characters outside
  `A-Za-z0-9 _.-`, deeper than 20 or longer than 400 chars) are rejected `400`.
  L5X files always collapse to a single logical `l5x/<name>` regardless of the
  folder they were uploaded from.
- **Building the file tree**: `GET /files` returns full paths — split each `path`
  on `/` to nest. Only `files/…` entries have real folders; an `l5x/<name>` entry
  is a single logical file (open its diff/views, don't expand it). Empty folders
  never appear (Git doesn't track them). URL-encode the slash-containing `path`
  query when calling `/files/raw` and the `/diff/*` endpoints. `modified_by` /
  `modified_at` can be empty for older data — treat as "unknown".
- **Storage quota**: an upload that would push the org over its quota returns
  `507`. Show remaining space from `GET /storage` (`used_bytes` / `limit_bytes`).
- **Branches list is now objects, not strings**: `GET /branches` returns
  `[Branch]` (tip commit, `is_default`, `is_protected`, `ahead`/`behind`,
  `merged`). The lightweight `branches` array on `Project` (`GET /projects/{id}`)
  stays a plain `[string]` for menus — use that when you only need names.
- **Branch delete is permanent**: `DELETE /branches/{branch}` force-deletes and
  can drop unmerged commits. The default branch and any protected branch return
  `400` — unprotect first (`PUT …/protection {"protected": false}`, owner/admin).
  Confirm in the UI, especially when `merged` is `false`.
- **Per-commit history**: list with `GET /commits?branch=`, open one with
  `GET /commits/{sha}` for its changed-files manifest, then drill in with
  `GET /commits/{sha}/diff/{changeset|ladder|text}?path=…` (same `path` values as
  `/diff`). These compare the commit to its **first parent**; a root commit
  compares to the empty tree, so its whole content shows as `added`.
- **Releases = tags**: `GET /tags` (newest first) backs the Tags card; its first
  entry — also `overview.latest_release` — is the "Latest release". A non-empty
  `message` on `POST /tags` makes an annotated release with notes; an empty one
  makes a lightweight tag (no notes). Deleting a tag is owner/admin only.

## What this adds, and what the UI can compute itself

This release enriches branches, adds branch delete/protection, per-commit detail
and diffs, and tags/releases. The short version of **why**: the old `/branches`
returned only names and there was no way to delete or protect a branch, inspect a
single commit, or cut a release — all of which the project pages (branch list,
commit history, "Latest release" + Tags card) need.

**How it works (server side).** Branches, commits, and tags are plain Git, so
almost everything is read straight from the repo with no new state:
`ahead`/`behind` come from `git rev-list --left-right --count main...<branch>`,
the tip commit from one `for-each-ref`, `files_changed` from a single
`git log --name-only` pass (merge commits are counted against their first
parent), per-commit diffs reuse the existing two-commit diff+cache by resolving
`base = <sha>^` (or the empty tree for a root commit), and releases are real Git
tags (annotated when you pass notes). The **one** thing Git can't represent is
**branch protection**, so that — and only that — is persisted in a small
`branch_protections` table; the default branch is protected implicitly.

**What the frontend should call the backend for** (server-authoritative — don't
recompute): `ahead`/`behind`, `files_changed`, the tip commit, `is_protected`,
and any diff. These need the Git history or the protection table.

**What the frontend can derive itself — and therefore should, to avoid a round
trip:**

- **`is_default`** is just `name === "main"` (the default branch). The API sends
  it for convenience, but you don't need a call to know it.
- **`merged`** is exactly `ahead === 0` (for a non-default branch with a tip).
  If you already have a `Branch`, you don't need a separate "is it merged?" call.
- **"Latest release"** is just `tags[0]` from `GET /tags` (newest first). Don't
  add a separate request — and on the landing page it's already in
  `overview.latest_release`, so the overview call alone covers it.
- **A commit's `files_changed` badge** equals `files.length` from its
  `CommitDetail`; if you've already loaded the detail, render the count from that
  rather than reading the field off the list row.
- **Grouping branches** into "active" vs. "merged" (the cleanup list) is a
  client-side `filter` on the `Branch[]` you already have (`merged && !is_default`)
  — no extra endpoint.
- **Tag/branch name validation** (non-empty, no spaces or `..`, doesn't start
  with `-`) can be checked in the form before submitting; the backend enforces it
  too and returns `400`, so this is just for a nicer error.

Rule of thumb: if the answer is a pure function of data the API already gave you
(`ahead`, the `tags` array, a branch's `name`), compute it in the client; if it
depends on Git history or stored protection state you don't have, ask the backend.

## PR review, comments, compare & activity

This release adds the collaboration layer: a review/approval workflow with a
real merge gate, threaded and change-anchored comments, a one-call Compare view,
account self-management, and a project activity feed. **Why:** a PR could only be
opened and merged — there was no way to require review, comment on a specific
rung, see a rolled-up "what changed", edit your profile, or audit who did what.

**How it works (server side).**
- **Approvals + merge gate.** A protected branch carries `required_approvals`.
  Each member can `approve` / `request-changes` (one verdict per person, stored
  in `pull_approvals`). `GET …/mergeability` runs a **lock-free conflict dry-run**
  (`git merge-tree --write-tree`, which merges in memory and touches nothing) and
  combines it with the approval count into `can_merge`. The `POST …/merge`
  endpoint **re-checks the gate itself** and returns `409` if approvals are short.
- **Comments.** One `comments` table gained `parent_id` (one-level threading) and
  nullable anchor fields (`path`/`routine`/`rung`/`sha`) for change-level
  comments. The list is a single indexed query and **batch-loads authors** (the
  old code did one query per comment).
- **Compare** aggregates the per-file `ChangeSet` you already compute into
  summary counts + impact rows; it caches by the commit pair like any diff.
- **Activity** is an append-only `activities` table written in the **same
  transaction** as each action, so the feed can't drift from reality. Reads are
  one indexed `(project_id, created_at)` query, gated by project membership.
- **Accounts**: `avatar` is a 3-char code (no image stored); `PATCH /auth/me`
  and `POST /auth/me/password` self-serve profile and password.

**The merge button — read this.** Gate the button on `mergeability.can_merge`,
but understand that's **UX only**: the backend independently enforces the
approval gate and conflict check on `POST …/merge`. Never treat a greyed button
as the security boundary — a direct call still gets `409` if the gate isn't met.

**Anchored comments — how the pin works.** A change-level comment stores *where*
on the diff it sits: the file (`l5x/<name>`), the routine, the rung's new-side
number, and the **commit sha it was made against**. The frontend supplies those
from the spot the user clicked; the backend just stores and returns them. Rung
numbers shift as a branch advances, so a comment is pinned to its `sha` — if the
PR head has moved past it, show it as "on an earlier version" rather than
mis-placing it.

**What the frontend can do itself — and should, to avoid a round trip:**

- **Nest comment threads** client-side. The API returns a **flat** `[Comment]`
  ordered by time; group by `parent_id` to build the two-level tree. No
  "get thread" endpoint exists because you already have everything in one call.
- **`approved` / `can_merge` math** is given to you (`approvals`,
  `required_approvals`), but if you mutate optimistically after an approve you can
  recompute `approved = approvals >= required_approvals` locally without re-fetching.
- **Avatars render entirely client-side** from the 3-char `avatar` code — no
  image request, no avatar endpoint. Decode base/colour/accessory from the code.
- **Pagers** come straight from the `X-Total-Count` header (`pages =
  ceil(total / limit)`); don't add a separate "count" call.
- **Reviewer/approver pickers**: load candidates once from `GET /projects/{id}/members`
  (or `GET /orgs/{id}/users` for the whole org) and filter in the client; both are
  indexed and fast, so there's no per-keystroke search endpoint to call.
- **Initials/empty states** (a user's display name, "no reviewers yet") are pure
  render from data you already hold.

What still must come from the backend: `mergeability` (needs Git + the gate),
the `Compare`/diff payloads (Git history), `is_protected`/`required_approvals`
(the protection table), and the `activity` feed (the audit table). Anything that
depends on Git state or stored policy is a server call; anything that's a pure
function of a payload you already have is a client computation.

## Quick start (fetch)

```js
const API = "http://localhost:8000";
// Accounts are admin-created (no signup); log in for a token.
const body = new URLSearchParams({ username: email, password });
const { access_token } = await (await fetch(`${API}/auth/login`, {
  method: "POST", body,
})).json();
const auth = { Authorization: `Bearer ${access_token}` };

// 1) Which files changed between two refs?
const { files } = await (await fetch(
  `${API}/projects/${id}/diff?base=main&head=feature/x`, { headers: auth }
)).json();

// 2) Drill into one changed L5X file (path comes from a manifest entry).
const changeSet = await (await fetch(
  `${API}/projects/${id}/diff/changeset?base=main&head=feature/x&path=l5x/Line1`,
  { headers: auth }
)).json();
const ladder = await (await fetch(
  `${API}/projects/${id}/diff/ladder?base=main&head=feature/x&path=l5x/Line1`,
  { headers: auth }
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
| `PLCVC_LOGIN_RATE_MAX` / `PLCVC_LOGIN_RATE_WINDOW_SECONDS` | Login attempts allowed per client IP per window (default 600 / 60s — a coarse flood guard, sized so a site behind one NAT never trips it) |
| `PLCVC_LOGIN_ACCOUNT_MAX` / `PLCVC_LOGIN_ACCOUNT_WINDOW_SECONDS` | Failed logins allowed per account (email) per window before that account is locked out with `429` (default 8 / 900s); a successful login clears it |
| `PLCVC_INVITE_RATE_MAX` / `PLCVC_INVITE_RATE_WINDOW_SECONDS` | Invite preview/accept calls per client IP per window (default 20 / 60s) |
| `PLCVC_MAX_UPLOAD_MB` | Max size of a single uploaded file (default 100). Per-file (→ `413`); the reverse proxy caps the whole request separately |
| `PLCVC_ORG_STORAGE_LIMIT_GB` | Per-organization storage cap in GB (default 2); counts the logical bytes of committed uploads (→ `507`); per-org overrides live on the org row |
| `PLCVC_DIFF_CACHE_MAX_MB` | Soft cap on the diff cache in MB (default 500); least-recently-used entries are evicted past it |
| `PLCVC_WEB_APP_URL` | Web-app base URL used to build the CLI device-login verification link (default `https://app.spykeautomation.com`) |
| `PLCVC_DEVICE_CODE_TTL_MINUTES` / `PLCVC_DEVICE_POLL_INTERVAL_SECONDS` | CLI device-login code lifetime and poll interval (default 10 / 5) |
| `PLCVC_DEVICE_RATE_MAX` / `PLCVC_DEVICE_RATE_WINDOW_SECONDS` | Device-auth calls per client IP per window (default 60 / 60s) |

---

## Changelog — endpoints added

A running log of new endpoints, so the frontend can track the contract. The
tables above are the canonical reference; this is the "what's new" view.

### 2026-06-26 · Branches, commits & releases

| Method | Path | What it adds |
|--------|------|--------------|
| `DELETE` | `/projects/{id}/branches/{branch}` | Delete a branch (blocked for default/protected) |
| `PUT` | `/projects/{id}/branches/{branch}/protection` | Protect/unprotect + set `required_approvals` |
| `GET` | `/projects/{id}/commits/{sha}` | Single-commit detail (files changed vs parent) |
| `GET` | `/projects/{id}/commits/{sha}/diff/changeset` | Per-commit semantic diff (parent → commit) |
| `GET` | `/projects/{id}/commits/{sha}/diff/ladder` | Per-commit ladder diff |
| `GET` | `/projects/{id}/commits/{sha}/diff/text` | Per-commit text diff |
| `GET` | `/projects/{id}/tags` | List tags / releases (newest first) |
| `POST` | `/projects/{id}/tags` | Cut a tag / release |
| `DELETE` | `/projects/{id}/tags/{name}` | Delete a tag (owner/admin) |

*Changed shapes:* `GET`/`POST /branches` now return enriched `[Branch]`
(tip commit, default/protected, `required_approvals`, ahead/behind, merged);
`GET /commits` tags each commit with `branch` + `files_changed`;
`RepositoryOverview` gains `latest_release`.

### 2026-06-26 · PR review, comments, compare, accounts & activity

| Method | Path | What it adds |
|--------|------|--------------|
| `PATCH` | `/auth/me` | Update your profile (name, 3-char `avatar`) |
| `POST` | `/auth/me/password` | Change your password |
| `GET` | `/orgs/{id}/users` | List users in an organization (paginated) |
| `PATCH` | `/projects/{id}/pulls/{n}` | Edit a PR's title/description |
| `DELETE` | `/projects/{id}/pulls/{n}` | Delete (abandon) an open PR |
| `POST` | `/projects/{id}/pulls/{n}/reviewers` | Invite a reviewer/approver |
| `DELETE` | `/projects/{id}/pulls/{n}/reviewers/{user_id}` | Uninvite a reviewer |
| `POST` | `/projects/{id}/pulls/{n}/approve` | Record an approval |
| `POST` | `/projects/{id}/pulls/{n}/request-changes` | Record a changes-requested verdict |
| `DELETE` | `/projects/{id}/pulls/{n}/review` | Withdraw your own verdict |
| `GET` | `/projects/{id}/pulls/{n}/mergeability` | Conflict dry-run + approval gate (`can_merge`) |
| `DELETE` | `/projects/{id}/pulls/{n}/comments/{cid}` | Delete a comment (author/manager) |
| `GET` | `/projects/{id}/compare` | Compare view model (summary + impact rows) |
| `GET` | `/projects/{id}/activity` | Project activity feed / audit log |

*Changed shapes:* `Pull` gains `updated_at`, `reviewers`, `reviews`,
`required_approvals`, `approvals`, `approved`; `POST .../merge` enforces the
approval gate (`409` if short). `Comment` gains `parent_id`, `anchor`,
`edited_at` (threaded + change-anchored), and `PATCH .../comments/{cid}` now
edits the body too (author only). `User` gains `avatar`. List endpoints
(`commits`, `pulls`, `comments`, `tags`, `activity`, `orgs/{id}/users`) take
`?limit=&offset=` and return `X-Total-Count`.

### 2026-07-09 · L5X sections & organizer detail

| Method | Path | What it adds |
|--------|------|--------------|
| `GET` | `/projects/{id}/l5x` | Raw sections of a parsed L5X at a ref (`section=controller\|datatypes\|tags\|modules\|aoi`, per-AOI via `&name=`) — the data for the organizer's detail tables. Cached per commit; list sections exclude measured-heavy per-entity fields (see `L5XSection`). |

*Changed shapes:* `ProjectTree` schema_version bumped to **3** — Data Types
now splits into User-Defined / Strings / Add-On-Defined subfolders, AOI nodes
carry their routines as children (no ladder-card identity), new Motion Groups
and Power-Up / Controller Fault Handler folders, and a task's program
references now carry the program's routine subtree under namespaced keys. The
flat Programs folder and all existing keys are unchanged.
