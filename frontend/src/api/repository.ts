// Types for the repository detail view. The backend doesn't expose commit /
// change-request / controller endpoints yet, so the page renders empty states
// until a real detail payload is available; this describes its shape.
import type { RepoStatus } from "./projects";
import type { Rung } from "./compare";

export interface Commit {
  hash: string; // short 7-char hash for display
  sha: string; // full hash for API calls
  message: string;
  author: string;
  branch: string;
  at: string; // ISO
  filesChanged?: number;
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
  inSync: boolean;
}

export interface RepoFiles {
  totalFiles: number;
  totalSize: string;
}

export type FileKind =
  | "program"
  | "routine"
  | "tags"
  | "io"
  | "hmi"
  | "document"
  | "udt";

// A file's rendered contents, shaped by what kind of file it is. PLC logic is
// shown as ladder; tabular files (tags, I/O, UDT members) as a table; notes as
// text; binary formats (e.g. HMI runtime) can't be rendered inline.
export interface LadderRoutine {
  name: string;
  rungs: Rung[];
}

export type FileContent =
  | { type: "ladder"; routines: LadderRoutine[] }
  | { type: "table"; columns: string[]; rows: string[][] }
  | { type: "text"; text: string }
  | { type: "binary"; note: string };

export interface FileEntry {
  name: string;
  kind: FileKind;
  description?: string;
  size: string;
  modifiedAt: string; // ISO
  modifiedBy: string;
  content?: FileContent; // present when a single file is opened
}

export const FILE_KIND_LABEL: Record<FileKind, string> = {
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
