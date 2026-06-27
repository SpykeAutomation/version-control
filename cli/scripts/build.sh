#!/usr/bin/env bash
# Cross-compile the Spyke CLI release binaries into dist/.
# Usage: scripts/build.sh [version]
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="${1:-$(git describe --tags --always 2>/dev/null || echo dev)}"
LDFLAGS="-s -w -X github.com/spykeautomation/spyke/internal/cli.version=${VERSION}"
OUT=dist
mkdir -p "$OUT"

# Windows is the primary target; the engine is cross-platform so the others are
# free.
build() {
  local goos=$1 goarch=$2 ext=$3
  local name="spyke_${goos}_${goarch}${ext}"
  echo "building $name"
  GOOS="$goos" GOARCH="$goarch" CGO_ENABLED=0 \
    go build -ldflags "$LDFLAGS" -o "$OUT/$name" ./cmd/spyke
}

build windows amd64 .exe
build windows arm64 .exe
build darwin  arm64 ""
build darwin  amd64 ""
build linux   amd64 ""

echo
echo "built ${VERSION} into $OUT/:"
ls -1 "$OUT"
( cd "$OUT" && shasum -a 256 spyke_* > checksums.txt && echo "wrote checksums.txt" )
