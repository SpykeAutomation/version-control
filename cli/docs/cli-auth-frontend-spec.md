# Frontend handoff — the `/cli-auth` approval page

**Audience:** the web-app developer. This is self-contained; you don't need to
know anything about the CLI's internals to build it. The web app is hosted at
`https://app.spykeautomation.com`; the API at `https://api.spykeautomation.com`.

## Purpose

When a user runs the Spyke CLI's `spyke login`, the CLI opens their browser to
this page so the **already-logged-in web-app user** can approve the CLI sign-in.
This is the only piece of the device-login flow the web app owns. **Existing
users only — there is no signup here.**

## Route & params

- **Route:** `/cli-auth` (a normal SPA route).
- **Query param:** `?code=<USER_CODE>` — a short, human-readable code like
  `WDJB-MJHT` that the CLI also printed in the terminal. If the param is missing
  (the user navigated manually), show an input box to paste the code.
- **Auth required:** the user must be logged in (have the app's bearer JWT). If
  not, send them through the normal login first, **preserving `?code=` across the
  redirect** so they land back here.

## Flow

1. On load, read `code` from the query string; show it prominently (read-only if
   present, an editable input if absent).
2. Show a confirm prompt, e.g.: *"A device is trying to sign in to Spyke as
   **&lt;your name / email&gt;**. Approve only if you just started `spyke login`
   on your own computer, and the code below matches your terminal."* — then the
   `user_code`.
3. Buttons: **Approve** and **Cancel**.
4. **Approve** → `POST {API_BASE}/auth/device/approve`
   - Headers: `Authorization: Bearer <the user's JWT>` (the app already has it).
   - Body: `{ "user_code": "<USER_CODE>" }`
   - `200` → show *"✓ You're all set — return to your terminal."* (The CLI is
     polling and will pick up the token automatically; nothing else to do.)
   - `400` (invalid/expired code) → *"This code is invalid or expired. Run
     `spyke login` again."*
   - `409` (already approved/used) → *"This request was already approved."*
5. **Cancel** → navigate away (no API call required).

## Contract this page depends on (built by the backend)

- `POST /auth/device/approve` — **auth required** — body `{ user_code }` →
  `200` success · `400` invalid/expired · `409` already approved.
- `API_BASE` is the same API origin the rest of the app uses
  (prod `https://api.spykeautomation.com`). Reuse the existing API client / auth
  context.
- The other device endpoints (`/auth/device/code`, `/auth/device/token`) are
  **CLI ↔ backend only — the frontend never calls them.**

## Security / UX notes

- The **visible Approve click on a matching `user_code` is the anti-phishing
  check** — never auto-approve straight from the query param.
- The page only ever handles the short `user_code`. It must **never see or handle
  the long `device_code` secret** (that lives only in the CLI and backend).
- One approve request per click; the backend rate-limits these.

---

### For reference: the backend endpoints the CLI expects (built separately, not by you)

These are listed only so the picture is complete — they are the backend
developer's responsibility, not the frontend's.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/auth/device/code` | none | CLI starts the flow; returns `device_code`, `user_code`, `verification_uri_complete` (= `https://app.spykeautomation.com/cli-auth?code=<user_code>`), `interval`, `expires_in`. |
| `POST` | `/auth/device/approve` | **bearer (this page calls it)** | Binds the `user_code` to the logged-in user. |
| `POST` | `/auth/device/token` | none | CLI polls with `device_code`; returns `{access_token}` once approved, else an `authorization_pending` / `slow_down` signal. |
