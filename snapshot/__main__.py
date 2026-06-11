"""Command-line entry point: turn an L5X export into a snapshot folder.

Usage:
    python -m snapshot PROJECT.L5X -o OUT_DIR
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from parsers.l5x import L5XParser

from .writer import write_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="snapshot",
        description="Parse an L5X export and write it as a snapshot folder.",
    )
    parser.add_argument("l5x_path", help="path to the L5X export, e.g. PROJECT.L5X")
    parser.add_argument(
        "-o",
        "--out",
        required=True,
        help="folder to write the snapshot into (created if missing)",
    )
    args = parser.parse_args(argv)

    try:
        doc = L5XParser().parse_file(args.l5x_path)
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        written = write_snapshot(doc, out_dir)
    except (OSError, SyntaxError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(written)} files to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
