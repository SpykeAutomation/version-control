// Types and data access for a commit's diff. There are two views of the same
// change: a ladder-diff IR for drawing rung-by-rung before/after panels, and a
// semantic change-set that lists what changed by entity (tags, routines, etc.).
// Both mirror the backend models; hand-written TS is the convention here.
import { apiFetch } from "./client";

// --- ladder IR types ---
// Ladder-diff IR (mirror of backend/diff/ladder_models.py). Hand-written TS is
// the convention in this repo (no codegen). Field names match the JSON exactly.
export type ElementStatus = "unchanged" | "added" | "removed" | "modified";
export type RungStatus = "unchanged" | "added" | "removed" | "modified" | "comment_changed";

export interface IROperand { label: string; value: string; changed: boolean; }
export interface IRElement {
  kind: "contact" | "coil" | "box" | "branch" | "raw";
  status: ElementStatus;
  io?: "input" | "output" | null;  // reads on the left, writes on the right
  form?: string | null;        // contact: "no"|"nc" ; coil: "ote"|"otl"|"otu"
  label?: string | null;       // contact / coil tag text
  mnemonic?: string | null;    // box instruction / AOI name
  operands?: IROperand[];      // box operand rows
  legs?: IRElement[][];        // branch: parallel legs (each a list of elements)
  text?: string | null;        // raw fallback, rendered verbatim
}
export interface IRRungDiff {
  status: RungStatus;
  old_number?: number | null;
  new_number?: number | null;
  old_comment?: string | null;
  new_comment?: string | null;
  before: IRElement[];         // drawn in the left/old panel
  after: IRElement[];          // drawn in the right/new panel
}
export interface IRRoutineSummary {
  rungs_modified: number; rungs_added: number; rungs_removed: number;
  additions: number; removals: number;
}
export interface IRRoutineLadderDiff {
  controller?: string | null; program?: string | null; routine?: string | null;
  routine_type: string;
  old_label?: string | null; new_label?: string | null;
  summary: IRRoutineSummary;
  rungs: IRRungDiff[];
}
export interface LadderDiffDoc {
  schema_version: number;
  commit?: string | null;
  routines: IRRoutineLadderDiff[];
}

// --- changeset types ---
// Semantic diff (mirror of backend/diff/models.py).
export interface FieldChange { path: string; old: unknown; new: unknown; }
export interface RungChange {
  kind: "added" | "removed" | "modified" | "comment_changed";
  old_number?: number | null; new_number?: number | null;
  old_text?: string | null; new_text?: string | null;
  old_comment?: string | null; new_comment?: string | null;
}
export interface LineChange {
  kind: "added" | "removed" | "modified";
  old_number?: number | null; new_number?: number | null;
  old_text?: string | null; new_text?: string | null;
}
export interface EntityChange { name: string; kind: "added" | "removed" | "modified"; fields: FieldChange[]; }
export interface RoutineChange {
  name: string; kind: "added" | "removed" | "modified"; routine_type?: string | null;
  fields: FieldChange[]; rungs: RungChange[]; lines: LineChange[];
  formatting_only: boolean; note?: string | null;
}
export interface ProgramChange {
  name: string; kind: "added" | "removed" | "modified";
  fields: FieldChange[]; tags: EntityChange[]; routines: RoutineChange[];
}
export interface ChangeSet {
  controller: FieldChange[]; modules: EntityChange[]; data_types: EntityChange[];
  add_on_instructions: EntityChange[]; controller_tags: EntityChange[];
  programs: ProgramChange[]; tasks: EntityChange[];
}

// --- API functions ---

// The semantic change-set for a commit: what changed by entity.
export async function getCommitDiff(
  projectId: number,
  sha: string,
): Promise<ChangeSet> {
  return apiFetch<ChangeSet>(`/projects/${projectId}/commits/${sha}/diff`);
}

// The ladder-diff IR for a commit: rung-by-rung before/after for each routine.
export async function getCommitLadderDiff(
  projectId: number,
  sha: string,
): Promise<LadderDiffDoc> {
  return apiFetch<LadderDiffDoc>(
    `/projects/${projectId}/commits/${sha}/diff/ladder`,
  );
}

// Generic diff between any two refs (base = current/old, head = proposed/new).
// Used when the commit page's Left selector picks a base other than the parent.
function refQuery(base: string, head: string): string {
  return `?base=${encodeURIComponent(base)}&head=${encodeURIComponent(head)}`;
}

export async function getDiff(
  projectId: number,
  base: string,
  head: string,
): Promise<ChangeSet> {
  return apiFetch<ChangeSet>(`/projects/${projectId}/diff${refQuery(base, head)}`);
}

export async function getLadderDiff(
  projectId: number,
  base: string,
  head: string,
): Promise<LadderDiffDoc> {
  return apiFetch<LadderDiffDoc>(
    `/projects/${projectId}/diff/ladder${refQuery(base, head)}`,
  );
}
