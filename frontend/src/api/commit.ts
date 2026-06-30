// Types and data access for the commit review view. The page reads a
// CommitDetail from getCommit(), mapped from the commit meta + ladder-diff
// endpoints. Ladder rungs reuse the IR model from ./diff so the panels share the
// LadderDiff renderer, and the file/routine grouping reuses the shapes from
// ./mergeRequest so the two review pages stay structurally aligned.
import { apiFetch } from "./client";
import { listCommits } from "./commits";
import { getCommitDiff, getCommitLadderDiff } from "./diff";
import type {
  ChangeSet,
  IRElement,
  IRRoutineLadderDiff,
} from "./diff";
import { getCommitTree } from "./tree";
import type { ProjectTree } from "./tree";
import type { MRComment, PRFile, PRRoutineChange } from "./mergeRequest";
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
  // Pre-loaded full routine content, keyed by routineKey(program, routine).
  // Empty for real commits, which fetch on demand via getRoutineContent.
  fullContent: Record<string, RoutineFull>;
}

// --- Backend wiring ---
interface CommitOut {
  sha: string;
  message: string;
  author: string;
  at: string;
}

function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

const EMPTY_CHANGESET: ChangeSet = {
  controller: [],
  modules: [],
  data_types: [],
  add_on_instructions: [],
  controller_tags: [],
  programs: [],
  tasks: [],
};

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
): CommitDetail {
  const idx = commits.findIndex((c) => c.sha === sha || shortSha(c.sha) === sha);
  const meta = idx >= 0 ? commits[idx] : null;
  const parent = idx >= 0 ? commits[idx + 1] : undefined;

  // Group the ladder routines under their controller (the L5X file). A commit is
  // one controller file, so all routines fall under one file entry.
  const files: PRFile[] =
    ladder.length === 0
      ? []
      : [
          {
            name: ladder[0].controller ?? "Controller",
            changes: ladder.map<PRRoutineChange>((r) => ({
              routine: r.routine ?? "Routine",
              kind: "ladder",
              controller: r.controller ?? undefined,
              program: r.program ?? undefined,
              ladder: r,
            })),
          },
        ];

  const view = deriveChangeView(changeSet);
  const message = meta?.message ?? `Commit ${shortSha(sha)}`;
  // Per-file +/- counts from the ladder diff: a wholly added or removed rung
  // counts all of its elements, a modified rung only those that changed. The
  // headline totals are the sum, so the tally is never misleadingly zero.
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
    filesChanged: view.files.length || files.length,
    additions,
    deletions,
    message,
    summary: summarizeChangeSet(changeSet),
    rungsChanged: view.summary.rungsChanged,
    routinesModified: view.summary.routinesChanged,
    commentCount: 0,
    files,
    comments: [],
    impactedTags: view.symbols,
    fileStats,
    tree,
    // Real commits fetch full routine content on demand via getRoutineContent.
    fullContent: {},
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
  const [perBranch, ladder, changeSet, tree] = await Promise.all([
    Promise.all(
      branches.map((b) =>
        listCommits(projectId, b).catch(() => [] as CommitOut[]),
      ),
    ),
    getCommitLadderDiff(projectId, sha)
      .then((d) => d.routines)
      .catch(() => [] as IRRoutineLadderDiff[]),
    getCommitDiff(projectId, sha).catch(() => EMPTY_CHANGESET),
    getCommitTree(projectId, sha).catch(() => emptyTree("Controller")),
  ]);

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
  return mapCommit(sha, branch, commits as CommitOut[], ladder, changeSet, tree);
}
