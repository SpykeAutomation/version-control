// Types and data access for the merge-request review view. The page reads a
// MergeRequest from getMergeRequest(): in demo mode it's canned data; against
// the real API it's mapped from the backend pull-request endpoints. Ladder
// rungs reuse the diff model from ./compare so the panels share one renderer.
import { apiFetch, ApiError } from "./client";
import { listProjects } from "./projects";
import type { Rung } from "./compare";
import type { IRElement, IRRoutineLadderDiff, IRRungDiff } from "./diff";

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
// the pull request and its comments. When the backend can't be reached the page
// falls back to a self-contained demo request so the review view is still
// explorable without a running server.
export async function getMergeRequest(
  slug: string,
  mrId: string,
): Promise<MergeRequest> {
  try {
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
  } catch (err) {
    // A status-0 ApiError means the server is unreachable (e.g. no backend in
    // local dev) — show the demo request rather than an error banner.
    if (err instanceof ApiError && err.status === 0) return demoPull(mrId);
    throw err;
  }
}

// --- Demo data ---
// A fully populated, synthetic pull request used when no backend is reachable.
// Everything here is invented sample content, not derived from any real file.
function prettyId(mrId: string): string {
  const m = mrId.match(/\d+/);
  return m ? `MR-${m[0].padStart(3, "0")}` : "MR-027";
}

// --- IR ladder builders (feed the shared LadderDiff renderer) ---
type ElStatus = IRElement["status"];

function contact(
  label: string,
  form: "no" | "nc",
  status: ElStatus = "unchanged",
): IRElement {
  return { kind: "contact", status, io: "input", form, label };
}

function coil(label: string, status: ElStatus = "unchanged"): IRElement {
  return { kind: "coil", status, io: "output", form: "ote", label };
}

function tonBox(preset: string, status: ElStatus): IRElement {
  return {
    kind: "box",
    status,
    io: "output",
    mnemonic: "TON",
    operands: [
      { label: "Timer", value: "Reject_Delay", changed: false },
      { label: "Preset", value: preset, changed: status !== "unchanged" },
      { label: "Accum", value: "0", changed: false },
    ],
  };
}

function modRung(
  oldNumber: number,
  before: IRElement[],
  after: IRElement[],
): IRRungDiff {
  return {
    status: "modified",
    old_number: oldNumber,
    new_number: oldNumber,
    before,
    after,
  };
}

function ladderRoutine(routine: string, rungs: IRRungDiff[]): IRRoutineLadderDiff {
  return {
    routine,
    routine_type: "rll",
    old_label: "main",
    new_label: "feature/reject-station",
    summary: {
      rungs_modified: rungs.length,
      rungs_added: 0,
      rungs_removed: 0,
      additions: 0,
      removals: 0,
    },
    rungs,
  };
}

export function demoPull(mrId: string): MergeRequest {
  const now = Date.now();
  const ago = (minutes: number) =>
    new Date(now - minutes * 60_000).toISOString();

  return {
    id: prettyId(mrId),
    title: "Add reject station logic",
    status: "review",
    sourceBranch: "feature/reject-station",
    targetBranch: "main",
    sourceCommits: 5,
    targetCommits: 128,
    sourceSha: "a1bc3d4",
    targetSha: "9f8e7d6",
    author: "Jamie Wilson",
    authorAt: ago(180),
    updatedAt: ago(120),
    reviewers: [
      { name: "Alex Davis", role: "Controls Engineer", state: "approved" },
      { name: "Morgan Green", role: "Senior Engineer", state: "review" },
      { name: "Sam Clark", role: "Controls Engineer", state: "pending" },
    ],
    summary:
      "Adds reject station control logic with photoeye interlock, increases reject delay to 3000 ms, and adds safety interlock before motor run.",
    bullets: [
      "Added reject photoeye interlock",
      "Increased reject delay from 2500 ms to 3000 ms",
      "Added E_Stop_OK safety interlock before Motor_Run",
    ],
    rungsChanged: 28,
    routinesModified: 1,
    commentCount: 7,
    safetyReview: true,
    files: [
      {
        name: "MainController.L5X",
        rungsChanged: 28,
        linesChanged: 2,
        changes: [
          {
            routine: "RejectControl",
            kind: "ladder",
            ladder: ladderRoutine("RejectControl", [
              modRung(
                13,
                [
                  contact("Conveyor_Run_Cmd", "no"),
                  contact("Reject_Enable", "no"),
                  contact("Jam_Sensor", "nc"),
                  coil("Reject_Active"),
                ],
                [
                  contact("Conveyor_Run_Cmd", "no"),
                  contact("Reject_Enable", "no"),
                  contact("Reject_Photoeye", "no", "added"),
                  contact("Jam_Sensor", "nc"),
                  coil("Reject_Active"),
                ],
              ),
              modRung(
                26,
                [
                  contact("Reject_Active", "no"),
                  tonBox("T#2500ms", "modified"),
                  coil("Reject_Delay_DN"),
                ],
                [
                  contact("Reject_Active", "no"),
                  tonBox("T#3000ms", "modified"),
                  coil("Reject_Delay_DN"),
                ],
              ),
              modRung(
                44,
                [
                  contact("Safety_OK", "no"),
                  contact("Conveyor_Run_Cmd", "no"),
                  coil("Motor_Run"),
                ],
                [
                  contact("Safety_OK", "no"),
                  contact("E_Stop_OK", "no", "added"),
                  contact("Conveyor_Run_Cmd", "no"),
                  coil("Motor_Run"),
                ],
              ),
            ]),
          },
          {
            routine: "RejectControl",
            kind: "structured",
            code: {
              routine: "RejectControl",
              changes: 1,
              marks: [null, "mod", null, null, null, "add"],
              left: {
                ref: "main",
                version: "main",
                lines: [
                  { ln: 28, kind: "context", text: "IF Reject_Active AND NOT Reject_Delay_DN THEN" },
                  { ln: 29, kind: "context", text: "    Reject_Delay(IN := TRUE, PT := ⟦T#2500ms⟧);" },
                  { ln: 30, kind: "context", text: "ELSE" },
                  { ln: 31, kind: "context", text: "    Reject_Delay(IN := FALSE);" },
                  { ln: 32, kind: "context", text: "END_IF;" },
                  { ln: 33, kind: "context", text: "Motor_Run := Safety_OK AND Conveyor_Run_Cmd;" },
                ],
              },
              right: {
                ref: "feature/reject-station",
                version: "latest",
                lines: [
                  { ln: 28, kind: "context", text: "IF Reject_Active AND NOT Reject_Delay_DN THEN" },
                  { ln: 29, kind: "context", text: "    Reject_Delay(IN := TRUE, PT := ⟦T#3000ms⟧);" },
                  { ln: 30, kind: "context", text: "ELSE" },
                  { ln: 31, kind: "context", text: "    Reject_Delay(IN := FALSE);" },
                  { ln: 32, kind: "context", text: "END_IF;" },
                  { ln: 33, kind: "context", text: "Motor_Run := Safety_OK AND ⟦E_Stop_OK⟧ AND Conveyor_Run_Cmd;" },
                ],
              },
            },
          },
        ],
      },
      {
        name: "SafetyController.L5X",
        rungsChanged: 1,
        changes: [
          {
            routine: "SafetyMonitor",
            kind: "ladder",
            ladder: ladderRoutine("SafetyMonitor", [
              modRung(
                6,
                [contact("E_Stop_OK", "no"), coil("Safety_OK")],
                [
                  contact("E_Stop_OK", "no"),
                  contact("Guard_Closed", "no", "added"),
                  coil("Safety_OK"),
                ],
              ),
            ]),
          },
        ],
      },
    ],
    comments: [
      {
        author: "Morgan Green",
        role: "Controls Engineer",
        on: "lines 28-33",
        at: ago(120),
        body: "Please confirm reject delay increase is validated on Line 3. 3 seconds will impact throughput.",
      },
      {
        author: "Jamie Wilson",
        role: "Author",
        isAuthor: true,
        on: "lines 45",
        at: ago(60),
        body: "Validated during bench test on Line 3 during FAT. No rejects missed with a 3s delay at max speed.",
      },
      {
        author: "Alex Davis",
        role: "Safety Engineer",
        on: "Network 45",
        at: ago(45),
        body: "E_Stop_OK interlock meets safety requirements. Please ensure the safety review is approved before merge.",
      },
    ],
    checks: [
      { label: "Lint passed", state: "passed" },
      { label: "Naming convention passed", state: "passed" },
      { label: "Safety review required", state: "warning" },
    ],
    impactedTags: [
      "Reject_Active",
      "Reject_Photoeye",
      "Reject_Delay",
      "E_Stop_OK",
      "Motor_Run",
      "Safety_OK",
    ],
  };
}
