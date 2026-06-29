// Types and data access for the merge-request review view. The page reads a
// MergeRequest from getMergeRequest(), mapped from the backend pull-request
// endpoints. Ladder rungs reuse the diff model from ./compare so the panels
// share one renderer.
import { apiFetch } from "./client";
import { displayName } from "./users";
import { listCommits } from "./commits";
import {
  getCommitDiff,
  getCommitLadderDiff,
  getDiff,
  getLadderDiff,
} from "./diff";
import type { Rung } from "./compare";
import type { ChangeSet, IRRoutineLadderDiff } from "./diff";
import { deriveChangeView, summarizeChangeSet } from "../lib/changeset";

export type MRStatus = "open" | "review" | "approved" | "changes" | "merged";

// Where a reviewer stands on the request.
export type ReviewState = "approved" | "review" | "pending" | "changes";

// Outcome of an automated or required check.
export type CheckState = "passed" | "warning" | "failed" | "pending";

// Per-row change marker shown in the centre gutter of a side-by-side diff:
// an addition, a modification, or a removal.
export type DiffMark = "add" | "mod" | "rem";

export interface MRReviewer {
  name: string;
  role: string;
  state: ReviewState;
}

export interface MRCheck {
  label: string;
  state: CheckState;
}

export interface MRComment {
  author: string;
  role: string;
  isAuthor?: boolean;
  on?: string; // network/routine the comment is anchored to, e.g. "Network 27"
  at: string; // ISO
  body: string;
}

// One side of a ladder diff (current vs proposed).
export interface MRLadderSide {
  ref: string; // e.g. "Current / main"
  version: string; // e.g. "r1.0.2"
  rungs: Rung[];
}

export interface MRLadderDiff {
  routine: string;
  networks: number;
  left: MRLadderSide;
  right: MRLadderSide;
  // One marker per aligned rung row (null where the rung is unchanged); drives
  // the centre-gutter badges between the two panels.
  marks?: (DiffMark | null)[];
}

// Structured-text diff: a line-oriented code diff per side.
export type CodeLineKind = "context" | "added" | "removed";

export interface CodeLine {
  ln: number; // line number on this side
  kind: CodeLineKind;
  text: string;
}

export interface MRCodeSide {
  ref: string;
  version: string;
  lines: CodeLine[];
}

export interface MRCodeDiff {
  routine: string;
  left: MRCodeSide;
  right: MRCodeSide;
  changes?: number; // number of changed lines, shown beside the routine name
  // One marker per aligned line row (null where the line is unchanged).
  marks?: (DiffMark | null)[];
}

// A pull request groups its changes by file. Each file lists the routines that
// changed inside it; a routine change is either a ladder diff or a
// structured-text diff.
export type RoutineDiffKind = "ladder" | "structured";

export interface PRRoutineChange {
  routine: string;
  kind: RoutineDiffKind;
  // Full identity, so a routine can be matched unambiguously even when two
  // programs hold routines of the same name. Optional: not every caller sets them.
  controller?: string;
  program?: string;
  ladder?: IRRoutineLadderDiff; // present when kind === "ladder"
  code?: MRCodeDiff; // present when kind === "structured"
}

export interface PRFile {
  name: string; // changed file name, e.g. "MainController.L5X"
  rungsChanged?: number;
  linesChanged?: number;
  changes: PRRoutineChange[];
}

// One commit on the source branch, as listed under the Commits tab. Mirrors the
// repository commit row: a full sha for the detail link, a short hash to show.
export interface MRCommitRow {
  sha: string; // full hash, used for the commit-detail link
  hash: string; // short hash for display
  message: string; // commit subject
  author: string;
  at: string; // ISO
  filesChanged?: number;
  additions?: number;
  deletions?: number;
}

export interface MergeRequest {
  id: string; // e.g. "MR-027"
  title: string;
  status: MRStatus;
  sourceBranch: string;
  targetBranch: string;
  sourceCommits: number;
  targetCommits: number;
  sourceSha?: string; // short SHA of the source branch tip
  targetSha?: string; // short SHA of the target branch tip
  author: string;
  authorAt: string; // ISO
  updatedAt: string; // ISO
  reviewers: MRReviewer[];
  summary: string;
  bullets: string[];
  rungsChanged: number;
  routinesModified: number;
  commentCount: number;
  safetyReview: boolean;
  // Changes grouped by file. Each file carries its own ladder / structured-text
  // routine diffs.
  files: PRFile[];
  // The commits on the source branch that this request would merge, newest first.
  commits: MRCommitRow[];
  comments: MRComment[];
  checks: MRCheck[];
  impactedTags: string[];
}

export const MR_STATUS_META: Record<MRStatus, { tone: string; label: string }> = {
  open: { tone: "orange", label: "Open" },
  review: { tone: "blue", label: "In review" },
  approved: { tone: "green", label: "Approved" },
  changes: { tone: "red", label: "Changes requested" },
  merged: { tone: "purple", label: "Merged" },
};

export const REVIEW_STATE_META: Record<ReviewState, { tone: string; label: string }> = {
  approved: { tone: "green", label: "Approved" },
  review: { tone: "orange", label: "In review" },
  changes: { tone: "red", label: "Changes" },
  pending: { tone: "gray", label: "Pending" },
};

export const CHECK_STATE_META: Record<CheckState, { tone: string; label: string }> = {
  passed: { tone: "green", label: "Passed" },
  warning: { tone: "orange", label: "Warning" },
  failed: { tone: "red", label: "Failed" },
  pending: { tone: "gray", label: "Pending" },
};

// --- Backend wiring ---
// Shapes returned by the backend pull-request endpoints (backend/app/schemas.py).
// The backend embeds people as nested user objects (first/last name, no single
// `name`); displayName() collapses one to a string.
interface PullUser {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
}
interface PullOut {
  number: number;
  title: string;
  description: string;
  source_branch: string;
  target_branch: string;
  status: string; // "open" | "merged" | ...
  author: PullUser;
  merge_sha: string | null;
  created_at: string;
}
interface CommentOut {
  id: number;
  author: PullUser;
  body: string;
  created_at: string;
}

const PULL_STATUS: Record<string, MRStatus> = {
  open: "review",
  merged: "merged",
  approved: "approved",
  closed: "changes",
};

function pullNumber(mrId: string): number {
  const m = mrId.match(/\d+/);
  return m ? parseInt(m[0], 10) : NaN;
}

// A row in a project's change-requests (pull-requests) list.
export interface ChangeRequestSummary {
  number: number;
  title: string;
  author: string;
  status: MRStatus;
  createdAt: string;
}

// List a project's change requests, newest first.
export async function listChangeRequests(
  projectId: number,
): Promise<ChangeRequestSummary[]> {
  const pulls = await apiFetch<PullOut[]>(`/projects/${projectId}/pulls`);
  return pulls.map((p) => ({
    number: p.number,
    title: p.title,
    author: p.author ? displayName(p.author) : "Unknown",
    status: PULL_STATUS[p.status] ?? "open",
    createdAt: p.created_at,
  }));
}

// Open a change request from one branch into another. Returns the new
// request's number so the caller can route to it.
export async function createChangeRequest(
  projectId: number,
  input: {
    title: string;
    description?: string;
    sourceBranch: string;
    targetBranch?: string;
  },
): Promise<{ number: number }> {
  return apiFetch<PullOut>(`/projects/${projectId}/pulls`, {
    method: "POST",
    json: {
      title: input.title,
      description: input.description ?? "",
      source_branch: input.sourceBranch,
      target_branch: input.targetBranch ?? "main",
    },
  });
}

// Invite a project member (by email) to review a change request. Best-effort:
// callers attach reviewers after the request is created and don't block on it.
export async function addReviewer(
  projectId: number,
  number: number,
  email: string,
): Promise<void> {
  await apiFetch(`/projects/${projectId}/pulls/${number}/reviewers`, {
    method: "POST",
    json: { email },
  });
}

// Result of merging a change request: either it landed (merged) or it stopped
// on conflicts. Mirrors the backend MergeResult schema.
export interface MergeOutcome {
  status: "merged" | "conflict";
  message: string;
  merge_sha?: string | null;
  conflicts?: string[];
}

// Merge a change request into its target branch. POSTs with no body; the
// backend reads the source/target from the stored pull request.
export async function mergeChangeRequest(
  projectId: number,
  number: number,
): Promise<MergeOutcome> {
  return apiFetch<MergeOutcome>(
    `/projects/${projectId}/pulls/${number}/merge`,
    { method: "POST" },
  );
}

// Post a thread-level comment on a merge request. The project id comes from the
// caller's cached project, so this makes no extra /projects request; it derives
// the pull number from the id, then POSTs to the pull request's comments endpoint.
export async function createComment(
  projectId: number,
  mrId: string,
  body: string,
): Promise<CommentOut> {
  const number = pullNumber(mrId);
  return apiFetch<CommentOut>(
    `/projects/${projectId}/pulls/${number}/comments`,
    { method: "POST", json: { body } },
  );
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

// Group the PR's changed routines under their controller (the L5X file). A
// project is one controller file, so every changed routine falls under a single
// file entry — the same grouping the commit-review page uses.
function ladderFiles(ladder: IRRoutineLadderDiff[]): PRFile[] {
  if (ladder.length === 0) return [];
  return [
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
}

// Map a backend pull request onto the page's view model. The changed files,
// ladder diffs, summary bullets, impacted tags and headline counts are derived
// from the PR's target -> source diff, so they reflect the real change. Reviewers
// and checks aren't in the backend contract yet, so they come back empty and the
// page renders empty states for them.
function mapPull(
  mrId: string,
  pull: PullOut,
  comments: CommentOut[],
  ladder: IRRoutineLadderDiff[],
  changeSet: ChangeSet,
  prCommits: MRCommitRow[],
  targetSha?: string,
): MergeRequest {
  const view = deriveChangeView(changeSet);
  return {
    id: mrId || `MR-${pull.number}`,
    title: pull.title,
    status: PULL_STATUS[pull.status] ?? "open",
    sourceBranch: pull.source_branch,
    targetBranch: pull.target_branch,
    sourceCommits: prCommits.length,
    targetCommits: 0,
    sourceSha: prCommits[0]?.hash,
    targetSha,
    author: displayName(pull.author),
    authorAt: pull.created_at,
    updatedAt: prCommits[0]?.at ?? pull.created_at,
    reviewers: [],
    summary: pull.description,
    bullets: summarizeChangeSet(changeSet),
    rungsChanged: view.summary.rungsChanged,
    routinesModified: view.summary.routinesChanged,
    commentCount: comments.length,
    safetyReview: false,
    files: ladderFiles(ladder),
    commits: prCommits,
    comments: comments.map((c) => ({
      author: displayName(c.author),
      role: c.author.id === pull.author.id ? "Author" : "Reviewer",
      isAuthor: c.author.id === pull.author.id,
      at: c.created_at,
      body: c.body,
    })),
    checks: [],
    impactedTags: view.symbols,
  };
}

// Load a merge request for the page. The project id comes from the caller's
// cached project, so this makes no extra /projects request; it fetches the pull
// request, its comments, the target -> source diff (ladder + change-set), and the
// commits the request would merge (source minus target).
export async function getMergeRequest(
  projectId: number,
  mrId: string,
): Promise<MergeRequest> {
  const number = pullNumber(mrId);

  const base = `/projects/${projectId}/pulls/${number}`;
  const pull = await apiFetch<PullOut>(base);

  // Once merged, the target branch already contains the change, so a
  // target -> source diff is empty. For a merged PR diff its merge commit against
  // its parent (what actually landed); for an open one diff target -> source.
  const merged = pull.status === "merged" && Boolean(pull.merge_sha);
  const ladderReq = merged
    ? getCommitLadderDiff(projectId, pull.merge_sha as string)
    : getLadderDiff(projectId, pull.target_branch, pull.source_branch);
  const changeReq = merged
    ? getCommitDiff(projectId, pull.merge_sha as string)
    : getDiff(projectId, pull.target_branch, pull.source_branch);

  const [comments, ladder, changeSet, srcCommits, tgtCommits] = await Promise.all([
    apiFetch<CommentOut[]>(`${base}/comments`).catch(() => [] as CommentOut[]),
    ladderReq.then((d) => d.routines).catch(() => [] as IRRoutineLadderDiff[]),
    changeReq.catch(() => EMPTY_CHANGESET),
    listCommits(projectId, pull.source_branch).catch(() => []),
    listCommits(projectId, pull.target_branch).catch(() => []),
  ]);

  // The commits this PR would merge: those on the source branch not already on
  // the target.
  const targetShas = new Set(tgtCommits.map((c) => c.sha));
  const prCommits: MRCommitRow[] = srcCommits
    .filter((c) => !targetShas.has(c.sha))
    .map((c) => ({
      sha: c.sha,
      hash: c.hash,
      message: c.message,
      author: c.author,
      at: c.at,
    }));

  return mapPull(
    mrId,
    pull,
    comments,
    ladder,
    changeSet,
    prCommits,
    tgtCommits[0]?.hash,
  );
}
