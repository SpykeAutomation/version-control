"""Snapshot folders: deterministic on-disk JSON form of a parsed L5X project."""
from .writer import SnapshotError, canonical_json, snapshot_document, write_snapshot

__all__ = ["SnapshotError", "canonical_json", "snapshot_document", "write_snapshot"]
