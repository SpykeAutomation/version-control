"""Command line for the converter.

    python -m ingest PROJECT.ACD [OUTPUT.L5X]

Prints the path of the written .L5X on success. Exit codes: 0 converted,
2 error.
"""
from __future__ import annotations

import argparse
import sys

from ingest.converter import _DEFAULT_TIMEOUT, acd_to_l5x


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ingest",
        description="Convert a Studio 5000 .ACD project file to .L5X.",
    )
    parser.add_argument("acd", help="path to the .ACD file")
    parser.add_argument(
        "l5x",
        nargs="?",
        default=None,
        help="where to write the .L5X (default: next to the .ACD)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_DEFAULT_TIMEOUT,
        help="seconds to wait for the conversion before giving up",
    )
    args = parser.parse_args(argv)

    try:
        target = acd_to_l5x(args.acd, args.l5x, timeout=args.timeout)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
