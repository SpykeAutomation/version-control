"""
Write a parsed L5X document to disk as a snapshot folder.

A snapshot is a folder of small JSON files, one logical entity per file,
always written the same way. Snapshotting two exports of an unchanged
project produces byte-identical folders, so the folder can live in git and
any real change shows up as a small diff on the file it belongs to.

Layout:

    controller.json                       metadata + controller settings
    modules.json                          I/O modules
    data_types.json                       UDTs
    aois/<name>.json                      one file per AOI
    tags.json                             controller-scoped tags
    programs/<name>/program.json          the program's own settings
    programs/<name>/tags.json             that program's tags
    programs/<name>/routines/<name>.json  one file per routine
    tasks.json                            tasks
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from parsers.l5x.models import L5XDocument

# The export timestamp changes on every export even when the project is
# unchanged, so it is dropped from snapshots. "When was this exported"
# belongs next to the snapshot (e.g. in the commit), not inside it.
_METADATA_EXCLUDE = {"export_date"}

# Top-level files and folders a snapshot owns. write_snapshot removes these
# before writing so files for deleted entities cannot linger; anything else
# in the output folder is left alone.
_MANAGED_FILES = (
    "controller.json",
    "modules.json",
    "data_types.json",
    "tags.json",
    "tasks.json",
)
_MANAGED_DIRS = ("aois", "programs")

# Names that become file names must be plain identifiers (letters, digits,
# underscore — what Logix allows). Anything else means corrupt input.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Windows reserves these device names — in any case, even with an extension.
# A file called AUX.json fails to create or silently vanishes on some
# systems, and a git checkout containing one breaks there too. Names like
# AUX are legal in Logix, so they are escaped, not rejected.
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


class SnapshotError(ValueError):
    """Raised when a document cannot be written as a snapshot folder."""


def canonical_json(data: object) -> str:
    """Render data as canonical JSON text.

    One fixed style everywhere: 2-space indent, keys in model field order
    (not sorted, so `name` stays first and diffs read well), non-ASCII text
    kept readable, and exactly one trailing newline.
    """
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _file_name(name: str) -> str:
    """Return the on-disk name for an entity.

    A Windows-reserved name gets a trailing hyphen ("AUX" becomes "AUX-").
    Hyphens cannot appear in Logix names, so the escaped name can never
    collide with a real one. The name inside the file stays unchanged.
    """
    if name.casefold() in _WINDOWS_RESERVED:
        return name + "-"
    return name


def _check_names(names: list[str], kind: str) -> None:
    """Reject names that cannot safely become file names in one folder."""
    seen: dict[str, str] = {}
    for name in names:
        if not _IDENTIFIER.match(name):
            raise SnapshotError(f"{kind} name {name!r} is not a valid identifier")
        # Windows file names are case-insensitive, so two names differing
        # only by case would silently collapse into one file.
        folded = name.casefold()
        if folded in seen:
            raise SnapshotError(
                f"{kind} names {seen[folded]!r} and {name!r} differ only by case"
            )
        seen[folded] = name


def snapshot_document(doc: L5XDocument) -> dict[str, str]:
    """Map a document to {relative file path: canonical JSON text}.

    Pure function — no disk access. Paths use forward slashes.
    """
    files: dict[str, str] = {}

    files["controller.json"] = canonical_json(
        {
            "metadata": doc.metadata.model_dump(mode="json", exclude=_METADATA_EXCLUDE),
            "controller": doc.controller.model_dump(mode="json"),
        }
    )
    files["modules.json"] = canonical_json(
        [m.model_dump(mode="json") for m in doc.modules]
    )
    files["data_types.json"] = canonical_json(
        [d.model_dump(mode="json") for d in doc.data_types]
    )
    files["tags.json"] = canonical_json(
        [t.model_dump(mode="json") for t in doc.controller_tags]
    )
    files["tasks.json"] = canonical_json([t.model_dump(mode="json") for t in doc.tasks])

    _check_names([a.name for a in doc.add_on_instructions], "AOI")
    for aoi in doc.add_on_instructions:
        files[f"aois/{_file_name(aoi.name)}.json"] = canonical_json(
            aoi.model_dump(mode="json")
        )

    _check_names([p.name for p in doc.programs], "Program")
    for program in doc.programs:
        base = f"programs/{_file_name(program.name)}"
        files[f"{base}/program.json"] = canonical_json(
            program.model_dump(mode="json", exclude={"tags", "routines"})
        )
        files[f"{base}/tags.json"] = canonical_json(
            [t.model_dump(mode="json") for t in program.tags]
        )
        _check_names([r.name for r in program.routines], "Routine")
        for routine in program.routines:
            files[f"{base}/routines/{_file_name(routine.name)}.json"] = canonical_json(
                routine.model_dump(mode="json")
            )

    return files


def write_snapshot(doc: L5XDocument, out_dir: Path | str) -> list[Path]:
    """Write the snapshot folder for a document, replacing any previous one.

    Only the files and folders a snapshot owns are removed first — the
    output folder itself may hold other things (a .git folder, notes) and
    those are left untouched. Files are written as UTF-8 with LF line
    endings on every platform. Returns the written paths, sorted.
    """
    out = Path(out_dir)
    files = snapshot_document(doc)  # build (and validate) before deleting anything

    for name in _MANAGED_DIRS:
        path = out / name
        if path.is_dir():
            shutil.rmtree(path)
    for name in _MANAGED_FILES:
        path = out / name
        if path.is_file():
            path.unlink()

    written: list[Path] = []
    for rel_path, text in files.items():
        path = out / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return sorted(written)
