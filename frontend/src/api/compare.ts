// Types for the Compare view. There is no comparison endpoint in the backend
// contract yet, so the page renders empty states until a real comparison is
// produced; these types describe the shape it will consume.

export type ChangeKind = "added" | "modified" | "removed";
export type Impact = "low" | "medium" | "high";

// A reference being compared (a branch/release pinned to a version).
export interface CompareRef {
  ref: string; // e.g. "main" or "feature/reject-station"
  version: string; // e.g. "v2.13.2" or "latest"
}

export interface ChangeSummary {
  rungsChanged: number;
  rungsModified: number;
  rungsAdded: number;
  rungsRemoved: number;
  networksAdded: number;
  instructionsAdded: number;
  commentsUpdated: number;
  safetyImpacting: number;
}

// --- Ladder model (drives the side-by-side diff panels) ---
export type ElementKind = "no" | "nc" | "coil" | "coil-set" | "timer" | "counter";
export type ElementState = "added" | "removed" | "unchanged";

export interface LadderElement {
  kind: ElementKind;
  tag: string;
  address: string;
  state?: ElementState; // element-level highlight; defaults to unchanged
}

export type RungState = "added" | "removed" | "modified" | "unchanged";

export interface Rung {
  number: number;
  state: RungState;
  elements: LadderElement[];
}

export interface RoutineSide {
  ref: string; // branch/release label, e.g. "Current / main"
  version: string;
  rungs: Rung[];
}

export interface RoutineDiff {
  routine: string; // routine/program name
  left: RoutineSide; // current
  right: RoutineSide; // proposed
}

// --- Change table / review ---
export interface ChangeRow {
  kind: ChangeKind;
  network: number;
  change: string; // short title, e.g. "Added rung"
  description: string;
  impact: Impact;
  author: string;
  at: string; // ISO timestamp
}

export interface ReviewComment {
  author: string;
  at: string; // ISO timestamp
  body: string;
  resolved?: boolean;
}

export interface FileAffected {
  name: string; // program/file name
  detail: string; // e.g. "Networks 14, 27, 45, 52"
}

export interface Comparison {
  repository: string;
  controller: string;
  left: CompareRef; // current
  right: CompareRef; // proposed
  summary: ChangeSummary;
  diff: RoutineDiff;
  changes: ChangeRow[];
  comments: ReviewComment[];
  symbols: string[]; // tags/symbols affected
  files: FileAffected[];
}

// ---- The real backend compare view (GET /projects/{id}/compare) ----
// Rolled-up summary + per-file impact rows for any ref pair. Field names match
// the backend JSON exactly (backend/README.md, "CompareView"). Used by the
// revert preview; the Compare page above still renders its local mock types.
import { apiFetch } from "./client";

export interface CompareViewSummary {
  commits: number;
  files_changed: number;
  l5x_changed: number;
  rungs_added: number;
  rungs_removed: number;
  rungs_modified: number;
  routines_modified: number;
  tags_impacted: number;
}

export interface CompareViewRow {
  path: string;
  kind: "l5x" | "file";
  change: "added" | "modified" | "removed";
  rungs_added: number;
  rungs_removed: number;
  rungs_modified: number;
  symbols: string[];
}

export interface CompareView {
  base: string;
  head: string;
  summary: CompareViewSummary;
  files: CompareViewRow[];
  affected_symbols: string[];
}

export function getCompareView(
  projectId: number,
  base: string,
  head: string,
): Promise<CompareView> {
  const q = `?base=${encodeURIComponent(base)}&head=${encodeURIComponent(head)}`;
  return apiFetch<CompareView>(`/projects/${projectId}/compare${q}`);
}
