// Types for the repository detail view. The backend doesn't expose commit /
// change-request / controller endpoints yet, so the page renders empty states
// until a real detail payload is available; this describes its shape.
import { ApiError } from "./client";
import { listProjects, type ProjectRow, type RepoStatus } from "./projects";
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
  lastBackup: string; // ISO; last upload pulled from the controller
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

// --- Demo data ---
// A fully populated, synthetic repository detail used when no backend is
// reachable. Everything here is invented sample content, not derived from any
// real file.
export function demoRepositoryDetail(): RepositoryDetail {
  const now = Date.now();
  const ago = (minutes: number) => new Date(now - minutes * 60_000).toISOString();

  const commits: Commit[] = [
    { hash: "a713c9d", sha: "a713c9d4e21f8b0c6a9d3e57c11b2f8a9d0e4c12",
      message: "Add jam detection timer", author: "Alex Davis", branch: "main",
      at: ago(120), filesChanged: 3 },
    { hash: "c2b91aa", sha: "c2b91aa8f0d34e1b7c5a206e9f4d1183ab77c9e0",
      message: "Interlock logic update", author: "Jamie Wilson", branch: "main",
      at: ago(60 * 9), filesChanged: 2 },
    { hash: "d9e4b7f", sha: "d9e4b7f1a3c08e6249bd5f72c0a1e83b4d6f2901",
      message: "Add reject confirmation signal", author: "Morgan Green",
      branch: "feature/reject-station", at: ago(60 * 24 * 2), filesChanged: 5 },
    { hash: "f1a8d22", sha: "f1a8d2270b94c5e3a16d8027fb5c4e91ad03762f",
      message: "Fix photoeye false trigger", author: "Sam Clark",
      branch: "hotfix/e-stop-alarm", at: ago(60 * 24 * 4), filesChanged: 1 },
    { hash: "b6c3d91", sha: "b6c3d915e7402af8c1d6b390e25f7a04c8b1d63e",
      message: "Initial commissioning changes", author: "Alex Davis",
      branch: "commissioning/line-3-startup", at: ago(60 * 24 * 7), filesChanged: 12 },
  ];

  const branches: BranchInfo[] = [
    { name: "main", isDefault: true, isProtected: true,
      lastCommitHash: "a713c9d", lastCommitMessage: "Add jam detection timer",
      author: "Alex Davis", at: ago(120), ahead: 0, behind: 0 },
    { name: "commissioning/line-3-startup", isProtected: false,
      lastCommitHash: "b6c3d91", lastCommitMessage: "Initial commissioning changes",
      author: "Alex Davis", at: ago(60 * 24 * 7), ahead: 12, behind: 0 },
    { name: "feature/reject-station", isProtected: false,
      lastCommitHash: "d9e4b7f", lastCommitMessage: "Add reject confirmation signal",
      author: "Morgan Green", at: ago(60 * 24 * 2), ahead: 5, behind: 2 },
    { name: "hotfix/e-stop-alarm", isProtected: false,
      lastCommitHash: "f1a8d22", lastCommitMessage: "Fix photoeye false trigger",
      author: "Sam Clark", at: ago(60 * 24 * 4), ahead: 1, behind: 1 },
  ];

  const changeRequests: ChangeRequestRow[] = [
    { id: "CR-027", title: "Add reject station logic", author: "Jamie Wilson",
      status: "open", at: ago(120) },
    { id: "CR-026", title: "Update safety interlocks", author: "Morgan Green",
      status: "review", at: ago(60 * 24) },
    { id: "CR-025", title: "Sensor calibration routine", author: "Sam Clark",
      status: "approved", at: ago(60 * 24 * 2) },
    { id: "CR-024", title: "HMI alarm text updates", author: "Alex Davis",
      status: "merged", at: ago(60 * 24 * 7) },
  ];

  const details: DetailField[] = [
    { label: "Description", value: "Controls program for Packaging Line 3 including conveyors, case packer and reject system." },
    { label: "Owner", value: "Alex Davis" },
    { label: "Created", value: "May 14, 2024" },
  ];

  const tags: RepoTag[] = [
    { label: "packaging", tone: "neutral" },
    { label: "line-3", tone: "neutral" },
    { label: "production", tone: "green" },
    { label: "critical", tone: "red" },
    { label: "siemens", tone: "neutral" },
  ];

  return {
    description: "Controls program for Packaging Line 3 including conveyors, case packer and reject system.",
    status: "production",
    controller: "Siemens S7-1500",
    controllerModel: "CPU 1516F-3 PN/DP",
    latestRelease: "v2.14.0",
    latestReleaseAt: "2026-06-17T00:00:00.000Z",
    lastCommitAt: ago(120),
    lastCommitAuthor: "Alex Davis",
    openChangeRequests: 3,
    unresolvedComments: 2,
    commits,
    branches,
    mergedBranches: [],
    changeRequests,
    details,
    tags,
    linkedController: {
      id: "PLC-PL3-01",
      online: true,
      ip: "10.10.3.15",
      lastSeen: ago(2),
      lastBackup: ago(135),
      inSync: true,
    },
    files: { totalFiles: 1248, totalSize: "48.3 MB" },
    fileList: [
      { name: "LineControl_Main.ap16", kind: "program",
        description: "Main line control program",
        size: "612 KB", modifiedAt: ago(120), modifiedBy: "Alex Davis" },
      { name: "RejectStation.ap16", kind: "program",
        description: "Reject station logic",
        size: "338 KB", modifiedAt: ago(60 * 24), modifiedBy: "Jamie Wilson" },
      { name: "SafetyLogic.ap16", kind: "program",
        description: "Safety interlocks and E-stops",
        size: "204 KB", modifiedAt: ago(60 * 24 * 2), modifiedBy: "Morgan Green" },
      { name: "Conveyor_Functions.ap16", kind: "routine",
        description: "Reusable conveyor functions",
        size: "96 KB", modifiedAt: ago(60 * 24 * 3), modifiedBy: "Sam Clark" },
      { name: "README.md", kind: "document",
        description: "Project overview and setup",
        size: "12 KB", modifiedAt: ago(60 * 24 * 7), modifiedBy: "Alex Davis" },
      { name: "IO_Map.csv", kind: "io",
        description: "I/O mapping table",
        size: "44 KB", modifiedAt: ago(60 * 24 * 7), modifiedBy: "Jamie Wilson" },
    ],
  };
}

// Map the sparse fields a ProjectRow can supply onto a RepositoryDetail. The
// backend has no rich detail endpoint, so commits/branches/change requests are
// left empty here — the page loads those from their own endpoints — and the
// controller/tags/linked-controller cards degrade to empty until a detail
// endpoint exists.
function mapRepository(row: ProjectRow): RepositoryDetail {
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

// Load a repository's detail: resolve the project by slug, then map what the
// project row exposes. When the backend can't be reached the page falls back to
// a self-contained demo repository so the detail view is still explorable.
export async function getRepository(slug: string): Promise<RepositoryDetail> {
  try {
    const projects = await listProjects();
    const project = projects.find((p) => p.slug === slug);
    if (!project) throw new Error("Repository not found");
    return mapRepository(project);
  } catch (err) {
    // A status-0 ApiError means the server is unreachable (e.g. no backend in
    // local dev) — show the demo repository rather than an error banner.
    if (err instanceof ApiError && err.status === 0) return demoRepositoryDetail();
    throw err;
  }
}
