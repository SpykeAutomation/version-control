"""Store deterministic PLC snapshots in a real Git repository.

This module is the first product-facing layer above the parser/snapshot/diff
engine: callers provide L5X files, and ProjectRepo commits the generated
snapshot files on normal Git branches.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile

from diff import ChangeSet, diff_documents
from parsers.l5x import L5XParser
from snapshot import read_snapshot, write_snapshot


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

    def commit_l5x(
        self,
        l5x_path: str | Path,
        *,
        branch: str,
        title: str,
        description: str = "",
    ) -> CommitInfo:
        """Parse one L5X file, snapshot it, and commit the result on branch."""
        self._ensure_repo()
        self._checkout_branch(branch)

        # Parsing and snapshotting process user-uploaded content, which can
        # fail in many ways (malformed XML, not an L5X, unsupported logic).
        # Translate all of those into ProjectRepoError so callers get one
        # clean "bad input" error instead of a leaked parser exception.
        try:
            doc = self.parser.parse_file(str(l5x_path))
            write_snapshot(doc, self.path)
        except ProjectRepoError:
            raise
        except Exception as exc:
            raise ProjectRepoError(f"could not parse L5X file: {exc}") from exc
        self._run("add", "-A")

        if not self._has_staged_changes():
            raise ProjectRepoError("no snapshot changes to commit")

        args = ["commit", "-m", title]
        if description.strip():
            args.extend(["-m", description.strip()])
        self._run(*args)

        return CommitInfo(sha=self.resolve_ref("HEAD"), branch=branch, title=title)

    def resolve_ref(self, ref: str = "HEAD") -> str:
        """Return the commit SHA for a branch, tag, or revision expression."""
        self._ensure_repo()
        return self._output("rev-parse", ref)

    def document_at(self, ref: str):
        """Read the snapshot stored at one Git ref as an L5XDocument."""
        self._ensure_repo()
        with tempfile.TemporaryDirectory(prefix="plc-snapshot-") as tmp:
            tmp_path = Path(tmp)
            self._run("worktree", "add", "--detach", str(tmp_path), ref)
            try:
                return read_snapshot(tmp_path)
            finally:
                self._run("worktree", "remove", "--force", str(tmp_path))

    def diff_refs(self, old_ref: str, new_ref: str) -> ChangeSet:
        """Compare the snapshots stored at two Git refs."""
        return diff_documents(self.document_at(old_ref), self.document_at(new_ref))

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

    def log(self, ref: str = "HEAD", *, limit: int = 50) -> list[CommitLog]:
        """Commit history for a branch/ref, newest first."""
        self._ensure_repo()
        fmt = "%H%x1f%an%x1f%aI%x1f%s%x1f%b%x1e"
        result = self._run("log", f"-n{limit}", f"--format={fmt}", ref, check=False)
        if result.returncode != 0:
            return []  # ref has no commits yet
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
                )
            )
        return commits

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
