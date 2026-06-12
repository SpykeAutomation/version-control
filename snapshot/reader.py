"""Read a snapshot folder back into a parsed document.

The reverse of write_snapshot. Entities that live one file each (AOIs,
programs, routines) come back in file-name order; the diff layer matches
entities by name, so the order does not matter. The name inside each file
is the real name, so escaped file names like AUX-.json need no special
handling here.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from parsers.l5x.models import L5XDocument

from .writer import SnapshotError


def _load_json(path: Path) -> object:
    """Read one snapshot file, or explain exactly which file is bad."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SnapshotError(f"snapshot is missing {path.name}") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"{path.name} is not valid JSON: {exc}") from None


def read_snapshot(folder: Path | str) -> L5XDocument:
    """Load a snapshot folder back into the same document the parser made.

    This is what lets two saved snapshots be compared — for example two
    revisions checked out from git — without needing the original L5X
    files. A folder that is missing files or contains broken JSON raises
    SnapshotError naming the bad file.
    """
    root = Path(folder)
    if not root.is_dir():
        raise SnapshotError(f"not a snapshot folder: {root}")

    controller_file = _load_json(root / "controller.json")
    data: dict = {
        "metadata": controller_file.get("metadata", {}),
        "controller": controller_file.get("controller", {}),
        "modules": _load_json(root / "modules.json"),
        "data_types": _load_json(root / "data_types.json"),
        "controller_tags": _load_json(root / "tags.json"),
        "tasks": _load_json(root / "tasks.json"),
        "add_on_instructions": [],
        "programs": [],
    }

    aois_dir = root / "aois"
    if aois_dir.is_dir():
        for path in sorted(aois_dir.glob("*.json")):
            data["add_on_instructions"].append(_load_json(path))

    programs_dir = root / "programs"
    if programs_dir.is_dir():
        for prog_dir in sorted(p for p in programs_dir.iterdir() if p.is_dir()):
            program = _load_json(prog_dir / "program.json")
            program["tags"] = _load_json(prog_dir / "tags.json")
            program["routines"] = []
            routines_dir = prog_dir / "routines"
            if routines_dir.is_dir():
                for path in sorted(routines_dir.glob("*.json")):
                    program["routines"].append(_load_json(path))
            data["programs"].append(program)

    try:
        return L5XDocument.model_validate(data)
    except ValidationError as exc:
        raise SnapshotError(f"snapshot does not match the document model: {exc}") from None
