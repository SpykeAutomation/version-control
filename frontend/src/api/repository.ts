// Types for the repository detail view. The backend doesn't expose commit /
// change-request / controller endpoints yet, so the page renders empty states
// until a real detail payload is available; this describes its shape.
import { type ProjectRow, type RepoStatus } from "./projects";

export interface Commit {
  hash: string; // short 7-char hash for display
  sha: string; // full hash for API calls
  message: string;
  author: string;
  branch: string;
  at: string; // ISO
  filesChanged?: number;
  // Parent shas, first parent first; empty for a root commit. Absent only in
  // mock/detail payloads that never carried them.
  parents?: string[];
}

export interface BranchInfo {
  name: string;
  isDefault?: boolean;
  isProtected: boolean;
  lastCommitHash: string;
  lastCommitMessage: string;
  author: string;
  at: string; // ISO
  ahead: number;
  behind: number;
}

export interface MergedBranch {
  name: string;
  into: string; // branch it was merged into, e.g. "main"
  at: string; // ISO
}

export type CRStatus = "open" | "review" | "approved" | "merged";

export interface ChangeRequestRow {
  id: string;
  title: string;
  author: string;
  status: CRStatus;
  at: string; // ISO
}

export interface DetailField {
  label: string;
  value: string;
}

export interface RepoTag {
  label: string;
  tone?: "green" | "red" | "blue" | "neutral";
}

export interface LinkedController {
  id: string;
  online: boolean;
  ip: string;
  lastSeen: string; // ISO
  lastBackup: string; // ISO; last upload pulled from the controller
  inSync: boolean;
}

export interface RepoFiles {
  totalFiles: number;
  totalSize: string;
}

export type FileKind =
  | "controller"
  | "program"
  | "routine"
  | "tags"
  | "io"
  | "hmi"
  | "document"
  | "udt";

export interface FileEntry {
  name: string;
  // Raw repo path ("l5x/<name>" or "files/<nested/path>") — keys the per-file
  // backend lookups (e.g. the controller identity of an L5X). Absent only in
  // mock detail payloads.
  path?: string;
  kind: FileKind;
  description?: string;
  size: string;
  modifiedAt: string; // ISO
  modifiedBy: string;
}

export const FILE_KIND_LABEL: Record<FileKind, string> = {
  controller: "Controller",
  program: "Program",
  routine: "Routine",
  tags: "Tag map",
  io: "I/O map",
  hmi: "HMI screen",
  document: "Document",
  udt: "UDT",
};

// The rich detail layered on top of a Project (name/slug/branches are real).
export interface RepositoryDetail {
  description: string;
  status: RepoStatus;
  controller: string;
  controllerModel: string;
  latestRelease: string;
  latestReleaseAt: string; // ISO date of the latest release
  lastCommitAt: string; // ISO
  lastCommitAuthor: string;
  openChangeRequests: number;
  unresolvedComments: number;
  commits: Commit[];
  branches: BranchInfo[];
  mergedBranches: MergedBranch[];
  changeRequests: ChangeRequestRow[];
  details: DetailField[];
  tags: RepoTag[];
  linkedController: LinkedController;
  files: RepoFiles;
  fileList: FileEntry[];
}

export const CR_META: Record<CRStatus, { tone: string; label: string }> = {
  open: { tone: "orange", label: "Open" },
  review: { tone: "blue", label: "In review" },
  approved: { tone: "green", label: "Approved" },
  merged: { tone: "purple", label: "Merged" },
};

// Map the sparse fields a ProjectRow can supply onto a RepositoryDetail. The
// backend has no rich detail endpoint, so commits/branches/change requests are
// left empty here — the page loads those from their own endpoints — and the
// controller/tags/linked-controller cards degrade to empty until a detail
// endpoint exists.
export function mapRepository(row: ProjectRow): RepositoryDetail {
  return {
    description: row.description ?? "",
    status: row.status ?? "draft",
    controller: row.controller ?? "—",
    controllerModel: row.controller_model ?? "—",
    latestRelease: row.latest_release ?? "—",
    latestReleaseAt: row.latest_release_at ?? "",
    lastCommitAt: row.updated_at ?? row.created_at,
    lastCommitAuthor: row.last_activity_by ?? row.owner ?? "—",
    openChangeRequests: row.open_changes ?? 0,
    unresolvedComments: 0,
    commits: [],
    branches: [],
    mergedBranches: [],
    changeRequests: [],
    details: [],
    tags: [],
    linkedController: { id: "—", online: false, ip: "—", lastSeen: "", lastBackup: "", inSync: false },
    files: { totalFiles: 0, totalSize: "—" },
    fileList: [],
  };
}

