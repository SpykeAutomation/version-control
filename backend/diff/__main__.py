"""Command-line entry point: compare two versions of a PLC project.

Usage:
    python -m diff OLD NEW [--json]

OLD and NEW are each an L5X export or a snapshot folder, in any mix.
Exit codes follow diff convention: 0 = no differences, 1 = differences
found, 2 = error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from parsers.l5x import L5XParser
from parsers.l5x.models import L5XDocument
from snapshot import read_snapshot

from .engine import diff_documents
from .ladder import build_ladder_document
from .render import render_text


def _load(path_text: str) -> L5XDocument:
    path = Path(path_text)
    if path.is_dir():
        return read_snapshot(path)
    if path.is_file():
        return L5XParser().parse_file(str(path))
    raise FileNotFoundError(f"no such file or folder: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="diff",
        description="Compare two versions of a PLC project "
        "(L5X exports or snapshot folders, in any mix).",
    )
    parser.add_argument("old", help="the older version: an L5X file or snapshot folder")
    parser.add_argument("new", help="the newer version: an L5X file or snapshot folder")
    parser.add_argument(
        "--json", action="store_true", help="print the result as JSON instead of text"
    )
    parser.add_argument(
        "--ladder-json",
        metavar="FILE",
        help="write the ladder-diff document (for the visual renderer) to FILE",
    )
    parser.add_argument("--old-label", help="version label for the old side (e.g. v14)")
    parser.add_argument("--new-label", help="version label for the new side (e.g. v15)")
    args = parser.parse_args(argv)

    try:
        old_doc = _load(args.old)
        new_doc = _load(args.new)
    except (OSError, SyntaxError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RecursionError:
        # Reached only by content kept as raw XML (FBD/SFC); parsed content
        # is depth-checked with a clear message before it gets this far.
        print("error: a file nests elements too deeply to process", file=sys.stderr)
        return 2

    if args.ladder_json:
        document = build_ladder_document(
            old_doc,
            new_doc,
            old_label=args.old_label or Path(args.old).stem,
            new_label=args.new_label or Path(args.new).stem,
        )
        Path(args.ladder_json).write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"wrote {len(document.routines)} ladder routine card(s) to {args.ladder_json}")
        return 0 if not document.routines else 1

    changes = diff_documents(old_doc, new_doc)
    print(changes.model_dump_json(indent=2) if args.json else render_text(changes))
    return 0 if changes.is_empty() else 1


if __name__ == "__main__":
    sys.exit(main())
