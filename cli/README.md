# spyke — a git-like CLI for the Spyke PLC version-control platform

`spyke` lets PLC engineers work the way they work in `git`: clone a project,
edit L5X files in Studio 5000, see what changed, commit, push, branch, and open
pull requests — all against the Spyke API.

> **The model:** the Spyke API is **not** a git remote. A commit is a whole-file
> upload; the server parses L5X into a semantic snapshot and does the real Git
> commit itself. `spyke` is a REST client that *emulates* a git UX over that API.

## Architecture (and why a GUI can reuse it)

Mirrors how git is built — a CLI-first engine that a GUI shells out to (the
GitHub-Desktop model):

- **`spykecore/`** — the reusable engine: the REST client, the `.spyke`
  workspace/sync engine, and the credential store. A future GUI can import it
  directly (Go) or shell out to the binary.
- **`internal/cli/`** — a thin [Cobra](https://github.com/spf13/cobra) front-end
  that parses args, calls the engine, and renders.
- **`--json` on every command** + stable exit codes — the machine contract a GUI
  parses (our equivalent of git's `--porcelain`). Data → stdout, progress →
  stderr.

Exit codes: `0` ok · `2` usage · `3` auth/forbidden · `4` conflict · `5`
not-found · `6` storage-quota · `7` file-too-large · `1` other.

## Install (Windows)

```powershell
irm https://get.spykeautomation.com/install.ps1 | iex
```

This drops `spyke.exe` in `%LOCALAPPDATA%\Programs\Spyke`, adds it to your PATH,
and installs PowerShell tab-completion. See [`scripts/install.ps1`](scripts/install.ps1).

## Build from source

```bash
# requires Go 1.22+
cd cli
go build -ldflags "-X github.com/spykeautomation/spyke/internal/cli.version=$(git describe --tags --always)" -o spyke ./cmd/spyke
```

Or use [`scripts/build.sh`](scripts/build.sh) to cross-compile the Windows
binaries.

## Logging in

`spyke login` opens your browser to approve the sign-in (OAuth 2.0 Device
Authorization Grant). For CI/headless use, `spyke login --password` (with
`SPYKE_EMAIL`/`SPYKE_PASSWORD`) or set `SPYKE_TOKEN` directly. The token is stored
in the Windows Credential Manager (a 0600 file on macOS/Linux for development).

The server defaults to `https://api.spykeautomation.com`; override per-command
with `--server`, per-shell with `SPYKE_SERVER`, or per-workspace via `.spyke/config`.

## Commands

| Command | What it does |
|---------|--------------|
| `spyke login` / `logout` / `whoami` | authenticate / clear token / show user |
| `spyke create <name> [dir]` | create a project and scaffold a workspace |
| `spyke clone <project-id> [dir]` | download a project into a new workspace |
| `spyke status` | show local changes + commits to push (works offline) |
| `spyke commit -m "msg" [paths…]` | queue a commit locally |
| `spyke push` | upload queued commits to the server |
| `spyke pull` | fast-forward the current branch from the server |
| `spyke branch [name] [--from] [--delete]` | list / create / delete branches |
| `spyke checkout <branch> [-b]` | switch branches, refresh the working tree |
| `spyke log [--branch]` | commit history |
| `spyke files [--ref]` / `spyke cat <repo-path> [--ref]` | list / download files |
| `spyke diff <base> <head> [path]` | changed-file manifest, or one file's diff |
| `spyke pr create\|list\|view\|diff\|approve\|request-changes\|merge\|comment` | pull requests |
| `spyke tag [name] [-m notes]` | list / cut releases |
| `spyke completion <shell>` | shell completion script |

A typical session:

```bash
spyke login
spyke clone 42 ./mixer
cd mixer
# edit Line1.L5X in Studio 5000
spyke status                 # Line1.L5X modified
spyke commit -m "Add gate permissive"
spyke push
spyke branch feature/x && spyke checkout feature/x
spyke pr create -t "Add gate" && spyke pr merge 1
```

## Known limitations (from the API model — surfaced, not hidden)

- **No delete / rename.** Uploads only add or modify. `spyke status` shows a
  locally deleted file, but `push` skips it (the API has no delete).
- **No local *semantic* diff.** The server diffs two *committed* refs only.
  `status` shows changed file **names**; the full ChangeSet/ladder is available
  via `spyke diff <base> <head> <path>` after pushing.
- **Merging is PR-only.** `spyke pr merge`; a conflict is a normal result (the PR
  stays open to resolve by pushing new commits), not a crash.

## Tests

```bash
go test ./...                      # unit tests (engine)
SPYKE_SERVER=http://localhost:8000 scripts/e2e.sh   # live integration (needs a running backend)
```
