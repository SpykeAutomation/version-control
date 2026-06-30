#!/usr/bin/env bash
# Live end-to-end test of the Spyke CLI against a running backend, mirroring the
# flow in backend/scripts/smoke_api.py. Drives the real binary the way a user
# would. Requires a running API and a seeded account.
#
#   SPYKE_SERVER=http://localhost:8000 \
#   SPYKE_EMAIL=alice@example.com SPYKE_PASSWORD=Abcdef123456 \
#     scripts/e2e.sh
set -euo pipefail

cd "$(dirname "$0")/.."

: "${SPYKE_SERVER:?set SPYKE_SERVER}"
: "${SPYKE_EMAIL:?set SPYKE_EMAIL}"
: "${SPYKE_PASSWORD:?set SPYKE_PASSWORD}"

WORK="$(mktemp -d)"
BIN="$WORK/spyke"
PROJ="$WORK/proj"

# Build with the normal HOME/GOPATH (so the module cache stays where it belongs),
# then isolate HOME so the credential store doesn't touch the real one.
go build -o "$BIN" ./cmd/spyke
export HOME="$WORK/home"; mkdir -p "$HOME"
spyke() { "$BIN" --server "$SPYKE_SERVER" "$@"; }
ws()    { "$BIN" --server "$SPYKE_SERVER" -C "$PROJ" "$@"; }

ok=0
check() { if eval "$2"; then echo "  [PASS] $1"; ok=$((ok+1)); else echo "  [FAIL] $1"; exit 1; fi; }

echo "== auth =="
spyke login --password >/dev/null
check "whoami works after login" 'spyke whoami | grep -q "@"'

echo "== create + write loop =="
NAME="CLI E2E $RANDOM"
spyke create "$NAME" "$PROJ" >/dev/null
printf "line one\n" > "$PROJ/notes.txt"
check "status shows the new file" 'ws status | grep -q "added:.*files/notes.txt"'
ws commit -m "Add notes" >/dev/null
check "status shows a pending commit" 'ws status | grep -q "1 local commit"'
ws push >/dev/null
check "status is clean after push" 'ws status | grep -q "working tree clean"'
check "log shows the commit" 'ws log | grep -q "Add notes"'

echo "== branch + checkout + second commit =="
ws checkout -b feature/x >/dev/null
printf "feature line\n" >> "$PROJ/notes.txt"
ws commit -m "Edit on feature" >/dev/null && ws push >/dev/null
ws checkout main >/dev/null
check "checkout main reverts the file" '! grep -q "feature line" "$PROJ/notes.txt"'
ws checkout feature/x >/dev/null
check "checkout feature restores the file" 'grep -q "feature line" "$PROJ/notes.txt"'

echo "== diff =="
check "ref manifest lists the changed file" 'ws diff main feature/x | grep -q "files/notes.txt"'
check "text diff shows the added line" 'ws diff main feature/x files/notes.txt | grep -q "feature line"'

echo "== pull request lifecycle =="
N=$(ws --json pr create --from feature/x --into main -t "Feature X" | /usr/bin/python3 -c 'import sys,json;print(json.load(sys.stdin)["number"])')
check "pr appears in the list" "ws pr list | grep -q '#${N}'"
ws pr merge "$N" >/dev/null
check "pr is merged" "ws pr list --status merged | grep -q '#${N}'"

echo "== tags =="
ws tag v0.1.0 -m "first" >/dev/null
check "tag is listed" 'ws tag | grep -q "v0.1.0"'

echo
echo "ALL $ok CHECKS PASSED"
chmod -R u+w "$WORK" 2>/dev/null || true
rm -rf "$WORK" || true
