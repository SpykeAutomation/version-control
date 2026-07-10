// Types and data access for a commit's project-organizer tree: the full
// Studio 5000 structure at the commit (Controller -> Tasks / Programs /
// Routines, plus Add-On Instructions, Data Types, Controller Tags, I/O), with
// each node tagged by what changed. Mirrors backend/app/tree.py; hand-written
// TS is the convention here (no codegen). Field names match the JSON exactly.
import { apiFetch } from "./client";

export type TreeNodeKind =
  | "controller"
  | "folder"
  | "program"
  | "routine"
  | "aoi"
  | "datatype"
  | "tag"
  | "module"
  | "task";
export type TreeStatus = "unchanged" | "added" | "removed" | "modified";

export interface TreeNode {
  key: string;
  label: string;
  kind: TreeNodeKind;
  status: TreeStatus;
  descendant_changed: boolean;
  routine_type?: string | null;
  // Set only on routine nodes; maps the node to its ladder-diff card.
  controller?: string | null;
  program?: string | null;
  routine?: string | null;
  children: TreeNode[];
}

export interface ProjectTree {
  schema_version: number;
  root: TreeNode;
}

// The tree endpoints organize a single L5X file, so they need its `path`. The
// changed file is read from the diff manifest (the commit detail, or the
// base..head manifest), then its tree is fetched. Projects can hold several L5X
// files; the organizer renders one root, so the first changed L5X is used.
async function firstChangedL5x(manifestUrl: string): Promise<string> {
  const manifest = await apiFetch<{ files: { path: string; kind: string }[] }>(
    manifestUrl,
  );
  const file = manifest.files.find((f) => f.kind === "l5x");
  if (!file) throw new Error("No L5X file changed");
  return file.path;
}

// The L5X file the commit page organizes: the first changed L5X, or — when the
// commit touched no L5X (e.g. images or documents only) — the project's first
// L5X present at the commit, so the Files tab still shows the full hierarchy.
// The same path keys the /l5x section fetches for the detail panels.
export async function resolveCommitL5xPath(
  projectId: number,
  sha: string,
): Promise<string> {
  try {
    return await firstChangedL5x(`/projects/${projectId}/commits/${sha}`);
  } catch {
    const listing = await apiFetch<{ files: { path: string; kind: string }[] }>(
      `/projects/${projectId}/files?ref=${encodeURIComponent(sha)}`,
    );
    const l5x = listing.files.find((f) => f.kind === "l5x");
    if (!l5x) throw new Error("No L5X file at this commit");
    return l5x.path;
  }
}

// The organizer tree for one commit, tagged by the diff against its parent.
// Pass `path` when the caller already resolved it (saves the manifest fetch).
export async function getCommitTree(
  projectId: number,
  sha: string,
  path?: string,
): Promise<ProjectTree> {
  const base = `/projects/${projectId}/commits/${sha}`;
  const p = path ?? (await resolveCommitL5xPath(projectId, sha));
  return apiFetch<ProjectTree>(`${base}/tree?path=${encodeURIComponent(p)}`);
}

// The organizer tree at `head`, tagged by the diff against `base`. Used when
// the commit page's Left selector picks a base other than the parent.
export async function getTree(
  projectId: number,
  base: string,
  head: string,
): Promise<ProjectTree> {
  const q = `?base=${encodeURIComponent(base)}&head=${encodeURIComponent(head)}`;
  const path = await firstChangedL5x(`/projects/${projectId}/diff${q}`);
  return apiFetch<ProjectTree>(
    `/projects/${projectId}/tree${q}&path=${encodeURIComponent(path)}`,
  );
}
