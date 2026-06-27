// Types and data access for the merge-request review view. The page reads a
// MergeRequest from getMergeRequest(), mapped from the backend pull-request
// endpoints. Ladder rungs reuse the diff model from ./compare so the panels
// share one renderer.
import { apiFetch } from "./client";
import { listProjects } from "./projects";
import type { Rung } from "./compare";
import type { IRRoutineLadderDiff } from "./diff";

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
interface PullUser {
  id: number;
  email: string;
  name: string;
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
    author: p.author?.name ?? "Unknown",
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

// Post a thread-level comment on a merge request. Resolves the project by slug
// (same as getMergeRequest), derives the pull number from the id, then POSTs to
// the pull request's comments endpoint.
export async function createComment(
  slug: string,
  mrId: string,
  body: string,
): Promise<CommentOut> {
  const number = pullNumber(mrId);
  const projects = await listProjects();
  const project = projects.find((p) => p.slug === slug);
  if (!project) throw new Error("Project not found");
  return apiFetch<CommentOut>(
    `/projects/${project.id}/pulls/${number}/comments`,
    { method: "POST", json: { body } },
  );
}

// Map a backend pull request (+ its comments) onto the page's view model.
// The rich review fields (reviewers, checks, tags, ladder/structured-text
// diffs) aren't in the backend contract yet, so they come back empty and the
// page renders empty states for them — same convention as ProjectRow.
function mapPull(mrId: string, pull: PullOut, comments: CommentOut[]): MergeRequest {
  return {
    id: mrId || `MR-${pull.number}`,
    title: pull.title,
    status: PULL_STATUS[pull.status] ?? "open",
    sourceBranch: pull.source_branch,
    targetBranch: pull.target_branch,
    sourceCommits: 0,
    targetCommits: 0,
    author: pull.author.name,
    authorAt: pull.created_at,
    updatedAt: pull.created_at,
    reviewers: [],
    summary: pull.description,
    bullets: [],
    rungsChanged: 0,
    routinesModified: 0,
    commentCount: comments.length,
    safetyReview: false,
    files: [],
    commits: [],
    comments: comments.map((c) => ({
      author: c.author.name,
      role: c.author.id === pull.author.id ? "Author" : "Reviewer",
      isAuthor: c.author.id === pull.author.id,
      at: c.created_at,
      body: c.body,
    })),
    checks: [],
    impactedTags: [],
  };
}

// Load a merge request for the page: resolve the project by slug, then fetch
// the pull request and its comments.
export async function getMergeRequest(
  slug: string,
  mrId: string,
): Promise<MergeRequest> {
  const number = pullNumber(mrId);
  const projects = await listProjects();
  const project = projects.find((p) => p.slug === slug);
  if (!project) throw new Error("Project not found");

  const base = `/projects/${project.id}/pulls/${number}`;
  const [pull, comments] = await Promise.all([
    apiFetch<PullOut>(base),
    apiFetch<CommentOut[]>(`${base}/comments`).catch(() => [] as CommentOut[]),
  ]);
  return mapPull(mrId, pull, comments);
}
