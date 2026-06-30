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
