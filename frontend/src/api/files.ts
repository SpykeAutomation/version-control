// Data access for a project's file listing at a ref (branch or commit). The
// backend returns every blob's full relative path under the project root, e.g.
// `l5x/Pump` or `files/docs/io.csv`; this maps those onto the FileEntry shape
// the FilesTable renders. Mirrors GET /projects/{id}/files (backend
// routers/projects.py); hand-written TS is the convention here.
import { apiFetch } from "./client";
import type { FileEntry, FileKind } from "./repository";
import { formatBytes } from "../lib/format";

// What the endpoint returns per file (FileEntry in backend/app/schemas.py).
interface FileOut {
  path: string; // "l5x/<name>" or "files/<nested/path>"
  kind: "l5x" | "file";
  size: number; // bytes
  modified_by: string;
  modified_at: string; // ISO-8601
}

// Drop the top-level container prefix so the table shows a clean name: L5X files
// list by their bare name; other files keep their folder structure under files/.
function stripPrefix(path: string): string {
  if (path.startsWith("l5x/")) return path.slice("l5x/".length);
  if (path.startsWith("files/")) return path.slice("files/".length);
  return path;
}

// The backend only distinguishes L5X projects from everything else. L5X maps to
// the controller kind; all other files fall back to a single neutral kind for
// now (no per-extension inference yet).
function fileKind(kind: FileOut["kind"]): FileKind {
  return kind === "l5x" ? "controller" : "document";
}

// The project's files at a ref (branch name or commit sha). Empty before the
// first commit on that ref.
export async function listProjectFiles(
  projectId: number,
  ref: string,
): Promise<FileEntry[]> {
  const data = await apiFetch<{ files: FileOut[] }>(
    `/projects/${projectId}/files?ref=${encodeURIComponent(ref)}`,
  );
  return data.files.map((f) => ({
    name: stripPrefix(f.path),
    path: f.path,
    kind: fileKind(f.kind),
    size: formatBytes(f.size),
    modifiedAt: f.modified_at,
    modifiedBy: f.modified_by,
  }));
}
