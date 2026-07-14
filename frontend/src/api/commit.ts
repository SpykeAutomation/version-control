// Types and data access for the commit review view. The page reads a
// CommitDetail from getCommit(), mapped from the commit meta + ladder-diff
// endpoints. Ladder rungs reuse the IR model from ./diff so the panels share the
// LadderDiff renderer, and the file/routine grouping reuses the shapes from
// ./mergeRequest so the two review pages stay structurally aligned.
import { apiFetch } from "./client";
import { listCommits } from "./commits";
import {
  EMPTY_CHANGESET,
  getCommitDiff,
  getCommitLadderDiff,
  getCommitManifest,
} from "./diff";
import type {
  ChangedFile,
  ChangeSet,
  IRElement,
  IRRoutineLadderDiff,
} from "./diff";
import { getCommitTree, resolveCommitL5xPath } from "./tree";
import type { ProjectTree } from "./tree";
import { ladderRoutineChanges } from "./mergeRequest";
import type {
  CodeLine,
  MRComment,
  PRFile,
  PRRoutineChange,
} from "./mergeRequest";
import { deriveChangeView, summarizeChangeSet } from "../lib/changeset";

// One changed file's line tally, shown in the rail's "Files changed" card.
export interface CommitFileStat {
  name: string;
  additions: number;
  deletions: number;
}

// The full, read-only content of one routine at a commit. Lets the Files tab
// open any routine, including unchanged ones, not just the ones that changed.
export interface RoutineFullLadder {
  kind: "ladder";
  ladder: IRRoutineLadderDiff; // all rungs status "unchanged"; rendered single-column
}
export interface RoutineFullCode {
  kind: "structured";
  ref: string; // header label, e.g. "Current (a7f3c9d)"
  lines: { ln: number; text: string }[];
}
export type RoutineFull = RoutineFullLadder | RoutineFullCode;

// Key a routine's full content by "program/routine".
export function routineKey(program: string, routine: string): string {
  return `${program}/${routine}`;
}

export interface CommitDetail {
  sha: string; // short sha, e.g. "a7f3c9d"
  title: string; // commit headline
  branch: string; // branch the commit is on
  author: string;
  authorRole: string;
  authoredAt: string; // ISO
  parentSha: string; // short sha of the parent commit
  filesChanged: number;
  additions: number;
  deletions: number;
  message: string; // commit message headline (repeated in the message card)
  summary: string[]; // bullet points describing the change
  rungsChanged: number;
  routinesModified: number;
  commentCount: number;
  // Changes grouped by file; each file carries ladder / structured-text routine
  // diffs (same shape the merge-request page uses).
  files: PRFile[];
  comments: MRComment[];
  impactedTags: string[];
  fileStats: CommitFileStat[]; // per-file +/- tallies for the rail
  // The full project-organizer tree at this commit, with each node tagged by
  // what changed. Drives the Files tab's navigation.
  tree: ProjectTree;
  // Manifest path (l5x/<name>) of the L5X file the tree organizes; keys the
  // /l5x section fetches behind the detail panels. Null when the commit has
  // no L5X to organize.
  l5xPath: string | null;
  // Pre-loaded full routine content, keyed by routineKey(program, routine).
  // Empty for real commits, which fetch on demand via getRoutineContent.
  fullContent: Record<string, RoutineFull>;
  // The raw semantic diff, kept for the Changes tab's non-routine sections
  // (controller properties, tags, modules, AOIs, tasks).
  changeSet: ChangeSet;
  // The commit's changed-files manifest; its kind:"file" entries drive the
  // Changes tab's text-diff sections for non-L5X files.
  changedFiles: ChangedFile[];
}

// --- Backend wiring ---
interface CommitOut {
  sha: string;
  message: string;
  author: string;
  at: string;
  filesChanged?: number;
}

function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

const emptyTree = (label: string): ProjectTree => ({
  schema_version: 1,
  root: {
    key: "root",
    label,
    kind: "controller",
    status: "unchanged",
    descendant_changed: false,
    children: [],
  },
});

// Count leaf elements (contacts, coils, boxes), recursing into branch legs.
function countElements(els: IRElement[]): number {
  let n = 0;
  for (const e of els) {
    if (e.kind === "branch") {
      for (const leg of e.legs ?? []) n += countElements(leg);
    } else {
      n += 1;
    }
  }
  return n;
}

// Count leaf elements with a given status (used for the changed parts of a
// modified rung), recursing into branch legs.
function countByStatus(els: IRElement[], status: string): number {
  let n = 0;
  for (const e of els) {
    if (e.kind === "branch") {
      for (const leg of e.legs ?? []) n += countByStatus(leg, status);
    } else if (e.status === status) {
      n += 1;
    }
  }
  return n;
}

// Structured-text routine diffs come from the change-set — the ladder document
// only carries RLL routines. Each changed line is one aligned row: a modified
// line pairs old/new, an added or removed line leaves the other side's slot
// empty (sparse arrays keep the row indexes aligned; the renderer skips holes).
function structuredChanges(
  cs: ChangeSet,
  oldRef: string,
  newRef: string,
): PRRoutineChange[] {
  const out: PRRoutineChange[] = [];
  for (const p of cs.programs) {
    for (const r of p.routines) {
      if (r.lines.length === 0) continue;
      const left: CodeLine[] = [];
      const right: CodeLine[] = [];
      r.lines.forEach((ln, row) => {
        if (ln.old_text != null) {
          left[row] = { ln: ln.old_number ?? 0, kind: "removed", text: ln.old_text };
        }
        if (ln.new_text != null) {
          right[row] = { ln: ln.new_number ?? 0, kind: "added", text: ln.new_text };
        }
      });
      out.push({
        routine: r.name,
        kind: "structured",
        program: p.name,
        code: {
          routine: r.name,
          left: { ref: oldRef, version: "", lines: left },
          right: { ref: newRef, version: "", lines: right },
          changes: r.lines.length,
        },
      });
    }
  }
  return out;
}

// Map a real commit (meta + ladder diff + semantic change-set) onto the page's
// view model. The summary bullets, impacted tags and headline counts are derived
// from the change-set (the semantic diff), so they reflect the actual commit.
// The remaining review fields (comments, per-file line tallies) aren't in the
// backend contract yet, so they come back empty — same convention as the
// merge-request map.
function mapCommit(
  sha: string,
  branch: string,
  commits: CommitOut[],
  ladder: IRRoutineLadderDiff[],
  changeSet: ChangeSet,
  tree: ProjectTree,
  l5xPath: string | null,
  changedFiles: ChangedFile[],
): CommitDetail {
  const idx = commits.findIndex((c) => c.sha === sha || shortSha(c.sha) === sha);
  const meta = idx >= 0 ? commits[idx] : null;
  const parent = idx >= 0 ? commits[idx + 1] : undefined;

  // Group the changed routines under their controller (the L5X file). A commit
  // is one controller file, so all routines fall under one file entry: ladder
  // diffs from the ladder document, structured text from the change-set.
  const routineChanges: PRRoutineChange[] = [
    ...ladderRoutineChanges(ladder),
    ...structuredChanges(
      changeSet,
      parent ? `Previous (${shortSha(parent.sha)})` : "Previous",
      `This commit (${shortSha(sha)})`,
    ),
  ];
  const files: PRFile[] =
    routineChanges.length === 0
      ? []
      : [
          {
            name:
              ladder[0]?.controller ??
              l5xPath?.replace(/^l5x\//, "") ??
              "Controller",
            changes: routineChanges,
          },
        ];

  const view = deriveChangeView(changeSet);
  const message = meta?.message ?? `Commit ${shortSha(sha)}`;
  // Per-file +/- counts from the diffs: a wholly added or removed rung counts
  // all of its elements, a modified rung only those that changed; structured
  // text counts its changed lines per side (forEach skips the alignment holes).
  // The headline totals are the sum, so the tally is never misleadingly zero.
  const fileStats: CommitFileStat[] = files.map((f) => {
    let add = 0;
    let del = 0;
    for (const change of f.changes) {
      for (const rung of change.ladder?.rungs ?? []) {
        add +=
          rung.status === "added"
            ? countElements(rung.after)
            : countByStatus(rung.after, "added");
        del +=
          rung.status === "removed"
            ? countElements(rung.before)
            : countByStatus(rung.before, "removed");
      }
      change.code?.right.lines.forEach(() => {
        add += 1;
      });
      change.code?.left.lines.forEach(() => {
        del += 1;
      });
    }
    return { name: f.name, additions: add, deletions: del };
  });
  const additions = fileStats.reduce((n, f) => n + f.additions, 0);
  const deletions = fileStats.reduce((n, f) => n + f.deletions, 0);
  return {
    sha: shortSha(sha),
    title: message,
    branch,
    author: meta?.author ?? "Unknown",
    authorRole: "",
    authoredAt: meta?.at ?? new Date(0).toISOString(),
    parentSha: parent ? shortSha(parent.sha) : "—",
    // Real files touched by the commit (the backend's per-commit tally), not
    // the count of changed components inside them — a single L5X edit is one
    // file, however many routines moved.
    filesChanged: meta?.filesChanged ?? files.length,
    additions,
    deletions,
    message,
    // Full bullet list — the view truncates and offers a "+N more" expander.
    summary: summarizeChangeSet(changeSet, Infinity),
    rungsChanged: view.summary.rungsChanged,
    routinesModified: view.summary.routinesChanged,
    commentCount: 0,
    files,
    comments: [],
    impactedTags: view.symbols,
    fileStats,
    tree,
    l5xPath,
    // Real commits fetch full routine content on demand via getRoutineContent.
    fullContent: {},
    changeSet,
    changedFiles,
  };
}

// Fetch one routine's full content at a commit. The backend endpoint
// is read-only and returns the whole routine, not a diff. Until it exists this
// rejects (404) and the Files tab falls back to a placeholder.
export async function getRoutineContent(
  projectId: number,
  sha: string,
  program: string,
  routine: string,
): Promise<RoutineFull> {
  const q = `?program=${encodeURIComponent(program)}&routine=${encodeURIComponent(routine)}`;
  return apiFetch<RoutineFull>(`/projects/${projectId}/commits/${sha}/routine${q}`);
}

// Load a commit for the review page. The project (id + branch list) is resolved
// by the caller from the cached project list, so this makes no extra /projects
// request — it just fetches the commit list (for meta) and the diffs.
export async function getCommit(
  projectId: number,
  projectBranches: string[],
  sha: string,
): Promise<CommitDetail> {
  const branches = projectBranches.length > 0 ? projectBranches : ["main"];

  // The commit's metadata and parent live in its branch history, which may not be
  // the first branch — so fetch every branch's log and use the one that contains
  // the commit. Otherwise author/date fall back to placeholders ("Unknown" / 1970).
  const [perBranch, ladder, changeSet, l5xPath, changedFiles] =
    await Promise.all([
      Promise.all(
        branches.map((b) =>
          listCommits(projectId, b).catch(() => [] as CommitOut[]),
        ),
      ),
      getCommitLadderDiff(projectId, sha)
        .then((d) => d.routines)
        .catch(() => [] as IRRoutineLadderDiff[]),
      getCommitDiff(projectId, sha).catch(() => EMPTY_CHANGESET),
      resolveCommitL5xPath(projectId, sha).catch(() => null),
      getCommitManifest(projectId, sha).catch(() => [] as ChangedFile[]),
    ]);
  const tree = l5xPath
    ? await getCommitTree(projectId, sha, l5xPath).catch(() =>
        emptyTree("Controller"),
      )
    : emptyTree("Controller");

  let branch = branches[0];
  let commits = perBranch[0] ?? [];
  for (let i = 0; i < branches.length; i++) {
    const list = perBranch[i] ?? [];
    if (list.some((c) => c.sha === sha || shortSha(c.sha) === sha)) {
      branch = branches[i];
      commits = list;
      break;
    }
  }
  return mapCommit(
    sha,
    branch,
    commits as CommitOut[],
    ladder,
    changeSet,
    tree,
    l5xPath,
    changedFiles,
  );
}
