"""Store deterministic PLC snapshots in a real Git repository.

This module is the first product-facing layer above the parser/snapshot/diff
engine: callers provide L5X files, and ProjectRepo commits the generated
snapshot files on normal Git branches.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from diff import ChangeSet, LadderDocument, build_ladder_document, diff_documents
from parsers.l5x import L5XParser
from parsers.l5x.models import Controller, ControllerMetadata, L5XDocument
from snapshot import read_snapshot, write_snapshot

# Files with these suffixes are parsed as L5X; everything else is stored as-is.
_L5X_SUFFIXES = {".l5x"}

# A logical file name (an L5X folder under l5x/, or a blob under files/) must be
# safe on every filesystem and in git, and stable across uploads so that
# re-uploading the same file versions the same path. We allow ordinary filename
# characters and reject anything else rather than silently transforming it.
_SAFE_NAME = re.compile(r"[A-Za-z0-9 _.-]+")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


class ProjectRepoError(RuntimeError):
    """Raised when a Git-backed project operation fails."""


@dataclass(frozen=True)
class CommitInfo:
    """One committed PLC snapshot."""

    sha: str
    branch: str
    title: str


@dataclass(frozen=True)
class CommitLog:
    """One commit's metadata, read back from Git history."""

    sha: str
    title: str
    description: str
    author: str
    date: str
    files_changed: int = 0  # logical files this commit changed vs its first parent


@dataclass(frozen=True)
class TagInfo:
    """One Git tag, as read back from the repo. Tags double as releases: an
    annotated tag carries its own tagger, date, and message (the release notes);
    a lightweight tag falls back to the target commit's committer and date."""

    name: str
    target_sha: str  # the commit the tag points to
    message: str  # annotation/notes (empty for a lightweight tag)
    tagger: str  # who created the annotated tag (else the commit's committer)
    date: str  # ISO-8601 tag date (annotated) or commit date (lightweight)
    annotated: bool


@dataclass(frozen=True)
class UploadSpec:
    """One file to commit: its bytes already spooled to local_path, plus the
    original upload filename (which decides L5X-vs-other and the stored path)."""

    local_path: Path
    filename: str


@dataclass(frozen=True)
class ChangedFile:
    """One logical file that differs between two refs (a diff-manifest entry)."""

    path: str  # "l5x/<name>" or "files/<name>"
    kind: str  # "l5x" | "file"
    change: str  # "added" | "modified" | "removed"


@dataclass(frozen=True)
class FileEntry:
    """One logical file present at a ref (a project-tree entry)."""

    path: str  # "l5x/<name>" or "files/<nested/path>"
    kind: str  # "l5x" | "file"
    size: int = 0  # bytes (for an L5X file, its original source.L5X size)
    modified_by: str = ""  # author of the last commit that touched it
    modified_at: str = ""  # ISO-8601 timestamp of that commit


# A tag/release name must be a valid, single git ref component: start with an
# alphanumeric (so it can't be read as a CLI flag), then word/dot/dash/slash, and
# never contain "..". This is deliberately stricter than git's own ref rules.
_TAG_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


def _check_tag_name(name: str) -> str:
    name = name.strip()
    if not _TAG_NAME.fullmatch(name) or ".." in name or name.endswith("/"):
        raise ProjectRepoError(f"invalid tag name: {name!r}")
    return name


def _is_l5x(filename: str) -> bool:
    return Path(filename).suffix.lower() in _L5X_SUFFIXES


def _l5x_name(filename: str) -> str:
    """Stable, filesystem-safe folder name for an uploaded L5X file (its stem)."""
    stem = Path(filename).stem.strip()
    if not stem or stem in {".", ".."} or not _SAFE_NAME.fullmatch(stem):
        raise ProjectRepoError(f"unsafe L5X file name: {filename!r}")
    if stem.casefold() in _WINDOWS_RESERVED:
        stem += "-"
    return stem


# Bounds on an uploaded file path so a pathological upload can't create an
# absurdly deep tree or an enormous path.
_MAX_FILE_DEPTH = 20
_MAX_FILE_PATH_LEN = 400


def _file_path(filename: str) -> str:
    """Safe *relative* path for a non-L5X file stored under files/.

    Preserves directory structure so an uploaded folder keeps its shape, while
    refusing anything that could escape files/ (absolute paths, '..' segments),
    an unsafe component name, or a reserved Windows name. Windows separators are
    normalised to '/'.
    """
    raw = filename.strip().replace("\\", "/")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if not parts or len(parts) > _MAX_FILE_DEPTH or len(raw) > _MAX_FILE_PATH_LEN:
        raise ProjectRepoError(f"unsafe file path: {filename!r}")
    for part in parts:
        if part == ".." or not _SAFE_NAME.fullmatch(part):
            raise ProjectRepoError(f"unsafe file path: {filename!r}")
        if part.casefold() in _WINDOWS_RESERVED:
            raise ProjectRepoError(f"reserved file name in path: {filename!r}")
    return "/".join(parts)


def _empty_like(doc: L5XDocument) -> L5XDocument:
    """A content-free document carrying the same controller name as `doc`.

    Used as the absent side when diffing an L5X file that was added or removed:
    every entity then shows as added/removed without a spurious controller
    rename appearing in the diff.
    """
    return L5XDocument(
        metadata=ControllerMetadata(), controller=Controller(name=doc.controller.name)
    )


class MergeConflict(ProjectRepoError):
    """Raised when a branch merge stops on conflicts and is rolled back."""

    def __init__(self, files: list[str]) -> None:
        self.files = files
        super().__init__("Merge conflict — resolve to be able to merge")


class ProjectRepo:
    """A working Git repository that stores one project's snapshot files.

    The repository root is owned by the snapshot writer. Uploaded L5X files
    should live outside this folder; only generated snapshot JSON belongs here.
    """

    # Git's well-known empty-tree object. Diffing a root commit against it makes
    # the whole commit show as added (a root commit has no parent to diff).
    EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

    def __init__(
        self,
        path: str | Path,
        *,
        parser: L5XParser | None = None,
        git: str = "git",
    ) -> None:
        self.path = Path(path)
        self.parser = parser or L5XParser()
        self.git = git

    def init(self, *, initial_branch: str = "main") -> None:
        """Create the Git repo if it does not already exist."""
        self.path.mkdir(parents=True, exist_ok=True)
        if (self.path / ".git").exists():
            return

        self._run_raw("init", "-b", initial_branch, str(self.path))
        # Local identity keeps automated test/dev commits independent of the
        # user's global Git config. The app can override this later per user.
        self._run("config", "user.name", "PLC Version Control")
        self._run("config", "user.email", "plc-version-control@example.invalid")

    def create_branch(self, name: str, start_point: str = "main") -> None:
        """Create a branch at an existing commit/ref."""
        self._ensure_repo()
        self._run("branch", name, start_point)

    def delete_branch(self, name: str, *, fallback: str = "main") -> None:
        """Force-delete a branch.

        Git refuses to delete the branch HEAD is on, so if it's checked out we
        first switch to `fallback` (the caller guarantees that isn't `name`).
        Uses `-D` (force): the caller has already enforced policy (not the
        default branch, not protected), so unmerged commits may be discarded.
        """
        self._ensure_repo()
        if not self.branch_exists(name):
            raise ProjectRepoError(f"unknown branch: {name}")
        if self.current_branch() == name:
            self._checkout_branch(fallback)
        self._run("branch", "-D", name)

    def commit_files(
        self,
        specs: Sequence[UploadSpec],
        *,
        branch: str,
        title: str,
        description: str = "",
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> CommitInfo:
        """Commit one or more uploaded files as a single commit on `branch`.

        L5X files (detected by extension) are parsed and stored as a
        deterministic snapshot under ``l5x/<name>/snapshot``, with the raw bytes
        kept beside them as ``l5x/<name>/source.L5X`` so the exact upload can be
        retrieved at any ref. Everything else is stored verbatim under
        ``files/``.

        Validation is atomic: every L5X is parsed *before* anything is written,
        so a single malformed file rejects the whole upload and leaves the tree
        untouched — matching Git's all-or-nothing commit semantics.
        """
        self._ensure_repo()
        if not specs:
            raise ProjectRepoError("no files to commit")
        self._checkout_branch(branch)

        # Plan + validate everything first. Parsing/snapshotting handles
        # user-uploaded content that can fail many ways (malformed XML, not an
        # L5X, unsupported logic); translate those into ProjectRepoError so the
        # caller gets one clean "bad input" error, and do it before any write.
        l5x_plan: list[tuple[str, Path, L5XDocument]] = []
        file_plan: list[tuple[str, Path]] = []
        seen_l5x: dict[str, str] = {}
        seen_file: dict[str, str] = {}
        for spec in specs:
            if _is_l5x(spec.filename):
                name = _l5x_name(spec.filename)
                if name.casefold() in seen_l5x:
                    raise ProjectRepoError(
                        f"two uploads map to the same L5X name {name!r}"
                    )
                seen_l5x[name.casefold()] = name
                try:
                    doc = self.parser.parse_file(str(spec.local_path))
                except Exception as exc:
                    raise ProjectRepoError(
                        f"could not parse L5X file {spec.filename!r}: {exc}"
                    ) from exc
                l5x_plan.append((name, spec.local_path, doc))
            else:
                rel = _file_path(spec.filename)
                if rel.casefold() in seen_file:
                    raise ProjectRepoError(
                        f"two uploads map to the same file path {rel!r}"
                    )
                seen_file[rel.casefold()] = rel
                file_plan.append((rel, spec.local_path))

        # Write pass — validation has already passed.
        for name, local_path, doc in l5x_plan:
            base = self.path / "l5x" / name
            try:
                write_snapshot(doc, base / "snapshot")
            except Exception as exc:
                raise ProjectRepoError(f"could not snapshot {name!r}: {exc}") from exc
            base.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local_path, base / "source.L5X")
        files_root = (self.path / "files").resolve()
        for rel, local_path in file_plan:
            dest = self.path / "files" / rel
            # Defence in depth: even after validation, never write outside files/.
            if not dest.resolve().is_relative_to(files_root):
                raise ProjectRepoError(f"unsafe file path: {rel!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local_path, dest)

        self._run("add", "-A")
        if not self._has_staged_changes():
            raise ProjectRepoError("no changes to commit")

        args = ["commit"]
        if author_name and author_email:
            args += ["--author", f"{author_name} <{author_email}>"]
        args += ["-m", title]
        if description.strip():
            args.extend(["-m", description.strip()])
        self._run(*args)

        return CommitInfo(sha=self.resolve_ref("HEAD"), branch=branch, title=title)

    def resolve_ref(self, ref: str = "HEAD") -> str:
        """Return the commit SHA for a branch, tag, or revision expression."""
        self._ensure_repo()
        return self._output("rev-parse", ref)

    def commit_parent(self, ref: str) -> str | None:
        """First-parent commit SHA of a commit, or None if it's a root commit."""
        self._ensure_repo()
        result = self._run(
            "rev-parse", "--verify", "--quiet", f"{ref}^1", check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def commit_diff_base(self, ref: str) -> str:
        """The ref to diff a single commit against: its first parent, or the
        empty tree for a root commit (so the root shows entirely as added)."""
        parent = self.commit_parent(ref)
        return parent if parent is not None else self.EMPTY_TREE

    def document_at(self, ref: str, name: str) -> L5XDocument | None:
        """Read the snapshot for one L5X file at a ref, or None if it is absent
        there (so callers can treat that as an add/remove)."""
        self._ensure_repo()
        snap_rel = f"l5x/{name}/snapshot"
        if not self._exists_at(ref, f"{snap_rel}/controller.json"):
            return None
        with tempfile.TemporaryDirectory(prefix="plc-snapshot-") as tmp:
            tmp_path = Path(tmp)
            self._run("worktree", "add", "--detach", str(tmp_path), ref)
            try:
                return read_snapshot(tmp_path / snap_rel)
            finally:
                self._run("worktree", "remove", "--force", str(tmp_path))

    def _resolve_pair(
        self, old_ref: str, new_ref: str, name: str
    ) -> tuple[L5XDocument, L5XDocument]:
        """Load one L5X file at both refs, substituting an empty document for
        the side where it does not exist (added/removed)."""
        old = self.document_at(old_ref, name)
        new = self.document_at(new_ref, name)
        if old is None and new is None:
            raise ProjectRepoError(f"no L5X file {name!r} at either ref")
        if old is None:
            old = _empty_like(new)
        if new is None:
            new = _empty_like(old)
        return old, new

    def diff_refs(self, old_ref: str, new_ref: str, name: str) -> ChangeSet:
        """Compare one L5X file's snapshots at two refs."""
        old, new = self._resolve_pair(old_ref, new_ref, name)
        return diff_documents(old, new)

    def ladder_diff_refs(
        self,
        old_ref: str,
        new_ref: str,
        name: str,
        *,
        old_label: str | None = None,
        new_label: str | None = None,
    ) -> LadderDocument:
        """Build the drawable ladder-diagram diff IR for one L5X file (visual view)."""
        old, new = self._resolve_pair(old_ref, new_ref, name)
        return build_ladder_document(
            old,
            new,
            old_label=old_label or old_ref,
            new_label=new_label or new_ref,
            commit=self.resolve_ref(new_ref),
        )

    def changed_files(self, base_ref: str, head_ref: str) -> list[ChangedFile]:
        """Logical files that differ between two refs — the diff manifest.

        L5X files (folders under l5x/) are reported per logical file: added or
        removed by set difference of the names present at each ref, modified if
        any path beneath them changed. Non-L5X blobs under files/ are reported
        straight from git's name-status.
        """
        self._ensure_repo()
        base_l5x = self._l5x_names_at(base_ref)
        head_l5x = self._l5x_names_at(head_ref)

        out = self._output("diff", "--name-status", base_ref, head_ref)
        touched_l5x: set[str] = set()
        file_changes: dict[str, str] = {}
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0][:1]
            path = parts[-1]  # for a rename, this is the new path
            if path.startswith("l5x/"):
                comps = path.split("/")
                if len(comps) >= 2:
                    touched_l5x.add(comps[1])
            elif path.startswith("files/"):
                file_changes[path] = {"A": "added", "D": "removed"}.get(
                    status, "modified"
                )

        result: list[ChangedFile] = []
        result += [ChangedFile(f"l5x/{n}", "l5x", "added") for n in sorted(head_l5x - base_l5x)]
        result += [ChangedFile(f"l5x/{n}", "l5x", "removed") for n in sorted(base_l5x - head_l5x)]
        result += [
            ChangedFile(f"l5x/{n}", "l5x", "modified")
            for n in sorted((base_l5x & head_l5x) & touched_l5x)
        ]
        result += [ChangedFile(p, "file", file_changes[p]) for p in sorted(file_changes)]
        return result

    def text_file_diff(
        self, base_ref: str, head_ref: str, path: str
    ) -> tuple[bool, str | None]:
        """Unified diff of a non-L5X file between two refs.

        Returns (is_binary, unified). For a binary file on either side the
        unified text is None (binaries have no meaningful line diff)."""
        self._ensure_repo()
        if self._blob_is_binary(head_ref, path) or self._blob_is_binary(base_ref, path):
            return True, None
        result = self._run(
            "diff", "--no-color", base_ref, head_ref, "--", path, check=False
        )
        if result.returncode not in (0, 1):
            raise ProjectRepoError(result.stderr.strip() or "git diff failed")
        return False, result.stdout

    def read_blob(self, ref: str, path: str) -> bytes:
        """Raw bytes of a tracked file at a ref (e.g. an original L5X upload)."""
        self._ensure_repo()
        if not self._exists_at(ref, path):
            raise ProjectRepoError(f"no file {path!r} at {ref}")
        return self._run_bytes("show", f"{ref}:{path}")

    def list_files(self, ref: str, *, with_history: bool = False) -> list[FileEntry]:
        """Logical files present at a ref: one entry per L5X file and files/ blob.

        Each entry carries its byte size (for an L5X file, the original
        source.L5X size). With `with_history`, modified_by/modified_at are filled
        from the last commit that touched the file — one extra history walk, so
        cheap callers (e.g. the overview's file count) leave it off."""
        self._ensure_repo()
        # `-l` adds the blob size column: "<mode> <type> <sha> <size>\t<path>".
        result = self._run("ls-tree", "-r", "-l", ref, check=False)
        if result.returncode != 0:
            return []
        sizes: dict[str, int] = {}
        for line in result.stdout.splitlines():
            meta, _, path = line.partition("\t")
            cols = meta.split()
            if not path or len(cols) < 4:
                continue
            try:
                sizes[path] = int(cols[3])
            except ValueError:
                sizes[path] = 0

        l5x_names: list[str] = []
        seen_l5x: set[str] = set()
        file_paths: list[str] = []
        for path in sorted(sizes):
            if path.startswith("l5x/"):
                comps = path.split("/")
                if len(comps) >= 2 and comps[1] not in seen_l5x:
                    seen_l5x.add(comps[1])
                    l5x_names.append(comps[1])
            elif path.startswith("files/"):
                file_paths.append(path)

        history = self._last_change_index(ref) if with_history else {}

        entries: list[FileEntry] = []
        for name in l5x_names:
            logical = f"l5x/{name}"
            by, at = history.get(logical, ("", ""))
            entries.append(
                FileEntry(logical, "l5x", sizes.get(f"{logical}/source.L5X", 0), by, at)
            )
        for path in file_paths:
            by, at = history.get(path, ("", ""))
            entries.append(FileEntry(path, "file", sizes.get(path, 0), by, at))
        return entries

    def _last_change_index(self, ref: str) -> dict[str, tuple[str, str]]:
        """Map each current logical file -> (author, ISO date) of the commit that
        last changed it. One history walk, newest first, so the first commit to
        touch a path wins; L5X sub-paths collapse onto their logical l5x/<name>."""
        sep = "\x01"
        result = self._run(
            "log", f"--format={sep}%an{sep}%aI", "--name-only", ref, check=False
        )
        if result.returncode != 0:
            return {}
        index: dict[str, tuple[str, str]] = {}
        author = date = ""
        for line in result.stdout.splitlines():
            if line.startswith(sep):
                _, author, date = line.split(sep)
                continue
            path = line.strip()
            if path.startswith("l5x/"):
                comps = path.split("/")
                if len(comps) < 2:
                    continue
                logical = f"l5x/{comps[1]}"
            elif path.startswith("files/"):
                logical = path
            else:
                continue
            index.setdefault(logical, (author, date))
        return index

    def _l5x_names_at(self, ref: str) -> set[str]:
        """Immediate child folder names under l5x/ at a ref (its L5X files)."""
        result = self._run("ls-tree", "--name-only", ref, "l5x/", check=False)
        if result.returncode != 0:
            return set()
        names: set[str] = set()
        for line in result.stdout.splitlines():
            entry = line.strip()
            if entry.startswith("l5x/"):
                comp = entry[len("l5x/") :].strip("/")
                if comp:
                    names.add(comp)
        return names

    def _exists_at(self, ref: str, path: str) -> bool:
        return self._run("cat-file", "-e", f"{ref}:{path}", check=False).returncode == 0

    def _blob_is_binary(self, ref: str, path: str) -> bool:
        if not self._exists_at(ref, path):
            return False
        return b"\x00" in self._run_bytes("show", f"{ref}:{path}")[:8000]

    def branch_exists(self, name: str) -> bool:
        self._ensure_repo()
        result = self._run(
            "rev-parse", "--verify", "--quiet", f"refs/heads/{name}", check=False
        )
        return result.returncode == 0

    def list_branches(self) -> list[str]:
        """All local branch names.

        Includes the current branch even before its first commit exists, so a
        brand-new repo still reports its initial branch (e.g. "main").
        """
        self._ensure_repo()
        out = self._output("for-each-ref", "--format=%(refname:short)", "refs/heads")
        names = {line for line in out.splitlines() if line}
        current = self.current_branch()
        if current:
            names.add(current)
        return sorted(names)

    def current_branch(self) -> str:
        self._ensure_repo()
        return self._output("branch", "--show-current")

    def branch_tips(self) -> dict[str, CommitLog]:
        """Map each local branch -> its tip commit (one `for-each-ref` call).

        An unborn branch (e.g. `main` before the first commit) has no tip and is
        simply absent from the map. `files_changed` is left 0 here (it would cost
        one extra history pass per branch); use `log()` when you need it.
        """
        self._ensure_repo()
        us, rs = "\x1f", "\x1e"
        fmt = (
            f"%(refname:short){us}%(objectname){us}%(authorname){us}"
            f"%(authordate:iso-strict){us}%(contents:subject){us}%(contents:body){rs}"
        )
        out = self._output("for-each-ref", f"--format={fmt}", "refs/heads")
        tips: dict[str, CommitLog] = {}
        for record in out.split(rs):
            record = record.strip("\n")
            if not record.strip():
                continue
            name, sha, author, date, subject, body = (record.split(us) + [""] * 6)[:6]
            tips[name] = CommitLog(
                sha=sha, title=subject, description=body.strip(),
                author=author, date=date,
            )
        return tips

    def ahead_behind(self, branch: str, base: str) -> tuple[int, int] | None:
        """(ahead, behind) commit counts of `branch` relative to `base`:
        commits on `branch` not on `base`, and vice-versa. None when either ref
        can't be resolved (e.g. an unborn base branch)."""
        self._ensure_repo()
        result = self._run(
            "rev-list", "--left-right", "--count", f"{base}...{branch}", check=False
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.split()
        if len(parts) != 2:
            return None
        behind, ahead = int(parts[0]), int(parts[1])
        return ahead, behind

    def log(
        self, ref: str = "HEAD", *, limit: int = 50, offset: int = 0
    ) -> list[CommitLog]:
        """Commit history for a branch/ref, newest first.

        `offset` skips that many of the newest commits (for pagination). Each
        entry's `files_changed` counts the *logical* files the commit touched vs
        its first parent (l5x/<name> collapses to one, files/* count
        individually) — the same counting `changed_files` uses, in one extra
        history pass.
        """
        self._ensure_repo()
        fmt = "%H%x1f%an%x1f%aI%x1f%s%x1f%b%x1e"
        result = self._run(
            "log", f"-n{limit}", f"--skip={offset}", f"--format={fmt}", ref,
            check=False,
        )
        if result.returncode != 0:
            return []  # ref has no commits yet
        counts = self._files_changed_counts(ref, limit, offset)
        commits: list[CommitLog] = []
        for record in result.stdout.split("\x1e"):
            record = record.strip("\n")
            if not record.strip():
                continue
            sha, author, date, title, body = (record.split("\x1f") + [""] * 5)[:5]
            commits.append(
                CommitLog(
                    sha=sha,
                    title=title,
                    description=body.strip(),
                    author=author,
                    date=date,
                    files_changed=counts.get(sha, 0),
                )
            )
        return commits

    def _files_changed_counts(
        self, ref: str, limit: int, offset: int = 0
    ) -> dict[str, int]:
        """Map each commit sha -> number of logical files it changed vs its first
        parent. One `git log --name-only` pass over the same window as `log()`;
        the root commit lists all of its files (all added). `--diff-merges=
        first-parent` makes a merge commit report the files it brought in (rather
        than git's empty default), so this agrees with the commit-detail diff."""
        result = self._run(
            "log", f"-n{limit}", f"--skip={offset}", "--format=%x1e%H",
            "--name-only", "--diff-merges=first-parent", ref, check=False,
        )
        if result.returncode != 0:
            return {}
        counts: dict[str, int] = {}
        for record in result.stdout.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            lines = record.split("\n")
            sha = lines[0].strip()
            if not sha:
                continue
            logical: set[str] = set()
            for path in lines[1:]:
                path = path.strip()
                if path.startswith("l5x/"):
                    comps = path.split("/")
                    if len(comps) >= 2:
                        logical.add(f"l5x/{comps[1]}")
                elif path.startswith("files/"):
                    logical.add(path)
            counts[sha] = len(logical)
        return counts

    def merge(self, source: str, target: str, *, message: str | None = None) -> str:
        """Merge source into target.

        Returns the resulting commit SHA. On conflicts the merge is rolled back
        and MergeConflict is raised, listing the files that could not be merged.
        """
        self._ensure_repo()
        if not self.branch_exists(source):
            raise ProjectRepoError(f"unknown source branch: {source}")
        if not self.branch_exists(target):
            raise ProjectRepoError(f"unknown target branch: {target}")

        self._checkout_branch(target)
        msg = message or f"Merge branch '{source}' into '{target}'"
        result = self._run("merge", "--no-ff", "-m", msg, source, check=False)
        if result.returncode != 0:
            conflicts = self._run(
                "diff", "--name-only", "--diff-filter=U", check=False
            ).stdout.split()
            self._run("merge", "--abort", check=False)
            raise MergeConflict(conflicts)
        return self.resolve_ref("HEAD")

    def merge_preview(self, target: str, source: str) -> tuple[bool, list[str]]:
        """Dry-run a merge of `source` into `target` *without touching anything*.

        Uses `git merge-tree --write-tree`, which computes the merge entirely
        in memory — no checkout, no commit, no working tree — so it needs no lock
        and is safe to run concurrently. Returns (mergeable, conflicted files).
        """
        self._ensure_repo()
        if not self._is_commitish(target) or not self._is_commitish(source):
            raise ProjectRepoError("unknown branch for merge preview")
        result = self._run(
            "merge-tree", "--write-tree", "--name-only", "--no-messages",
            target, source, check=False,
        )
        if result.returncode == 0:
            return True, []
        # Non-zero with a written tree means conflicts: the first line is the
        # tree OID, the rest (until a blank line) are the conflicted paths.
        conflicts: list[str] = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                break
            conflicts.append(line)
        return False, conflicts

    def commit_count(self, base: str, head: str) -> int:
        """Number of commits reachable from `head` but not `base` (base..head)."""
        return self._rev_list_count(f"{base}..{head}")

    def commit_total(self, ref: str) -> int:
        """Total number of commits reachable from `ref` (0 if it has none yet)."""
        return self._rev_list_count(ref)

    def _rev_list_count(self, *spec: str) -> int:
        self._ensure_repo()
        result = self._run("rev-list", "--count", *spec, check=False)
        if result.returncode != 0:
            return 0
        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0

    # --- tags / releases ---------------------------------------------------
    def tag_exists(self, name: str) -> bool:
        self._ensure_repo()
        return self._run(
            "rev-parse", "--verify", "--quiet", f"refs/tags/{name}", check=False
        ).returncode == 0

    def create_tag(
        self,
        name: str,
        ref: str = "main",
        *,
        message: str = "",
        tagger_name: str | None = None,
        tagger_email: str | None = None,
    ) -> TagInfo:
        """Create a tag (a release) at `ref`.

        A non-empty `message` makes an *annotated* tag that records its own
        tagger and date plus the message as release notes; an empty message
        makes a lightweight tag that inherits the target commit's committer and
        date. `tagger_name`/`tagger_email` attribute an annotated tag to the
        real user (otherwise the repo's identity is used).
        """
        self._ensure_repo()
        name = _check_tag_name(name)
        if self.tag_exists(name):
            raise ProjectRepoError(f"tag already exists: {name}")
        if not self.branch_exists(ref) and not self._is_commitish(ref):
            raise ProjectRepoError(f"unknown ref: {ref}")
        args: list[str] = []
        message = message.strip()
        if message and tagger_name and tagger_email:
            args += ["-c", f"user.name={tagger_name}", "-c", f"user.email={tagger_email}"]
        args += ["tag"]
        if message:
            args += ["-a", name, "-m", message]
        else:
            args += [name]
        args += [ref]
        self._run(*args)
        for tag in self.list_tags():
            if tag.name == name:
                return tag
        raise ProjectRepoError(f"tag not found after creation: {name}")

    def delete_tag(self, name: str) -> None:
        self._ensure_repo()
        if not self.tag_exists(name):
            raise ProjectRepoError(f"unknown tag: {name}")
        self._run("tag", "-d", name)

    def list_tags(self) -> list[TagInfo]:
        """All tags, newest first by creation date (the tag date for annotated
        tags, the commit date for lightweight ones), ties broken by name. One
        `for-each-ref` call; only an annotated tag's own message is release
        notes (a lightweight tag's `contents` is just the commit's, so it's
        reported with no notes)."""
        self._ensure_repo()
        us, rs = "\x1f", "\x1e"
        fmt = (
            f"%(refname:short){us}%(objecttype){us}%(objectname){us}"
            f"%(*objectname){us}%(creatordate:iso-strict){us}%(taggername){us}"
            f"%(*committername){us}%(committername){us}"
            f"%(contents:subject){us}%(contents:body){rs}"
        )
        out = self._output("for-each-ref", f"--format={fmt}", "refs/tags")
        tags: list[TagInfo] = []
        for record in out.split(rs):
            record = record.strip("\n")
            if not record.strip():
                continue
            fields = (record.split(us) + [""] * 10)[:10]
            (name, objtype, objname, deref_name, date, taggername,
             deref_committer, committer, subject, body) = fields
            annotated = objtype == "tag"
            target = deref_name or objname
            tagger = taggername or deref_committer or committer
            if annotated:
                message = subject + (f"\n\n{body.strip()}" if body.strip() else "")
            else:
                message = ""  # lightweight tag: no notes of its own
            tags.append(
                TagInfo(
                    name=name,
                    target_sha=target,
                    message=message.strip(),
                    tagger=tagger,
                    date=date,
                    annotated=annotated,
                )
            )
        # ISO-8601 dates sort lexicographically; name is a stable tiebreaker.
        tags.sort(key=lambda t: (t.date, t.name), reverse=True)
        return tags

    def _is_commitish(self, ref: str) -> bool:
        return self._run(
            "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False
        ).returncode == 0

    def _has_staged_changes(self) -> bool:
        result = self._run("diff", "--cached", "--quiet", check=False)
        if result.returncode == 0:
            return False
        if result.returncode == 1:
            return True
        raise ProjectRepoError(result.stderr.strip() or "git diff failed")

    def _checkout_branch(self, branch: str) -> None:
        # In a newly initialized repo, HEAD can already point at the requested
        # branch before the first commit exists. `git checkout main` then fails
        # because there is no commit yet, but no checkout is actually needed.
        if self._output("branch", "--show-current") == branch:
            return
        self._run("checkout", branch)

    def _ensure_repo(self) -> None:
        if not (self.path / ".git").exists():
            raise ProjectRepoError(f"not a Git project repo: {self.path}")

    def _output(self, *args: str) -> str:
        return self._run(*args).stdout.strip()

    def _run_bytes(self, *args: str) -> bytes:
        """Run a git command capturing raw bytes (for binary blob contents)."""
        result = subprocess.run(
            [self.git, "-C", str(self.path), *args],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise ProjectRepoError(detail or f"git {' '.join(args)} failed")
        return result.stdout

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self._run_raw("-C", str(self.path), *args, check=check)

    def _run_raw(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [self.git, *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise ProjectRepoError(detail or f"git {' '.join(args)} failed")
        return result
