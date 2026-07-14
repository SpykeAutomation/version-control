// The backend compare view (GET /projects/{id}/compare): rolled-up summary +
// per-file impact rows for any ref pair. Field names match the backend JSON
// exactly (backend/README.md, "CompareView"). Used by the revert preview.
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
