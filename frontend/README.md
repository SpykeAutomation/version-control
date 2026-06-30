# Spyke frontend

Vite + React + TypeScript app for the Spyke web UI. It talks to the backend
HTTP API (see `../backend/README.md`) over JWT bearer headers.

## Develop

```bash
npm install
cp .env.example .env.local
npm run dev                  # http://localhost:5173
```

By default the dev server proxies API calls to the hosted backend
(`api.spykeautomation.com`), so `npm run dev` works with no local backend. The
browser only ever talks to `localhost:5173`; the dev server forwards the API
paths (`/auth`, `/projects`, `/health`) to the backend, so the hosted CORS
allow-list (which only permits `app.spykeautomation.com`) doesn't get in the
way. Leave `VITE_API_URL` empty for this to work — that's what makes the client
send same-origin relative requests.

To test against a backend running on your own machine instead, set
`VITE_PROXY_TARGET=http://localhost:8000` in `.env.local` and run the backend
with `PLCVC_CORS_ORIGINS=http://localhost:5173`.

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — type-check and build for production
- `npm run typecheck` — type-check only

## Deployment

The app is served at **`app.spykeautomation.com`** — its own subdomain, separate
from the marketing site (`spykeautomation.com`) and the backend
(`api.spykeautomation.com`). The marketing site's "Log In" button links to
`https://app.spykeautomation.com/login`.

Two things the host must do:

1. **Point `VITE_API_URL` at the backend.** `.env.production` already sets
   `https://api.spykeautomation.com`, and the backend must allow this origin:
   `PLCVC_CORS_ORIGINS=https://app.spykeautomation.com`.
2. **Serve `index.html` for every path (SPA fallback).** The app uses
   client-side routes (`/login`, `/onboarding`, …), so a direct request to any
   of them must return `index.html` or it will 404. With Caddy, for example:

   ```
   app.spykeautomation.com {
     root * /srv/app
     try_files {path} /index.html
     file_server
   }
   ```

Build with `npm run build`; deploy the `dist/` folder.

Access is **invite-only** during early access: the login screen has no public
sign-up link (it points people to request access on the marketing site). The
`/signup` route still exists for a future invite-acceptance flow but isn't
linked from the UI.

## What's here

The onboarding flow: sign in, sign up, create your first project, and a
confirmation screen.

- `src/api` — backend client (auth + projects)
- `src/auth` — auth context and route guard
- `src/pages` — one file per screen
- `src/components`, `src/layouts` — shared UI
