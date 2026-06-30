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
//
// The diff is per file: the manifest endpoint lists which files changed, then
// each L5X file is drilled into with its own `path` for the change-set and
// ladder views (see backend README). A project can hold several L5X files, so
// these resolve every changed L5X from the manifest and merge the results.

// A changed-file entry from a diff manifest (also a commit's file list).
interface ChangedFile {
  path: string;
  kind: "l5x" | "file";
  change: "added" | "modified" | "removed";
  views: string[];
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

function mergeChangeSets(sets: ChangeSet[]): ChangeSet {
  return {
    controller: sets.flatMap((s) => s.controller),
    modules: sets.flatMap((s) => s.modules),
    data_types: sets.flatMap((s) => s.data_types),
    add_on_instructions: sets.flatMap((s) => s.add_on_instructions),
    controller_tags: sets.flatMap((s) => s.controller_tags),
    programs: sets.flatMap((s) => s.programs),
    tasks: sets.flatMap((s) => s.tasks),
  };
}

// The L5X file paths that changed, from a manifest ({files:[...]}) or a commit
// detail (also {files:[...]}).
async function changedL5xPaths(manifestUrl: string): Promise<string[]> {
  const manifest = await apiFetch<{ files: ChangedFile[] }>(manifestUrl);
  return manifest.files.filter((f) => f.kind === "l5x").map((f) => f.path);
}

function refQuery(base: string, head: string): string {
  return `?base=${encodeURIComponent(base)}&head=${encodeURIComponent(head)}`;
}

// The semantic change-set for a commit: what changed by entity, across every
// L5X file the commit touched (vs its parent).
export async function getCommitDiff(
  projectId: number,
  sha: string,
): Promise<ChangeSet> {
  // The manifest of changed files is the commit detail itself ({files:[...]});
  // each file's change-set hangs off .../diff/changeset.
  const base = `/projects/${projectId}/commits/${sha}`;
  const paths = await changedL5xPaths(base);
  const sets = await Promise.all(
    paths.map((p) =>
      apiFetch<ChangeSet>(`${base}/diff/changeset?path=${encodeURIComponent(p)}`),
    ),
  );
  return mergeChangeSets(sets.length ? sets : [EMPTY_CHANGESET]);
}

// The ladder-diff IR for a commit: rung-by-rung before/after for each changed
// routine, across every L5X file the commit touched.
export async function getCommitLadderDiff(
  projectId: number,
  sha: string,
): Promise<LadderDiffDoc> {
  const base = `/projects/${projectId}/commits/${sha}`;
  const paths = await changedL5xPaths(base);
  const docs = await Promise.all(
    paths.map((p) =>
      apiFetch<LadderDiffDoc>(`${base}/diff/ladder?path=${encodeURIComponent(p)}`),
    ),
  );
  return {
    schema_version: docs[0]?.schema_version ?? 1,
    commit: sha,
    routines: docs.flatMap((d) => d.routines),
  };
}

// Generic change-set between any two refs (base = current/old, head =
// proposed/new), merged across every changed L5X file.
export async function getDiff(
  projectId: number,
  base: string,
  head: string,
): Promise<ChangeSet> {
  const q = refQuery(base, head);
  const paths = await changedL5xPaths(`/projects/${projectId}/diff${q}`);
  const sets = await Promise.all(
    paths.map((p) =>
      apiFetch<ChangeSet>(
        `/projects/${projectId}/diff/changeset${q}&path=${encodeURIComponent(p)}`,
      ),
    ),
  );
  return mergeChangeSets(sets.length ? sets : [EMPTY_CHANGESET]);
}

export async function getLadderDiff(
  projectId: number,
  base: string,
  head: string,
): Promise<LadderDiffDoc> {
  const q = refQuery(base, head);
  const paths = await changedL5xPaths(`/projects/${projectId}/diff${q}`);
  const docs = await Promise.all(
    paths.map((p) =>
      apiFetch<LadderDiffDoc>(
        `/projects/${projectId}/diff/ladder${q}&path=${encodeURIComponent(p)}`,
      ),
    ),
  );
  return {
    schema_version: docs[0]?.schema_version ?? 1,
    commit: null,
    routines: docs.flatMap((d) => d.routines),
  };
}
