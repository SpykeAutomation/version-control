import { apiFetch } from "./client";
import type { Commit } from "./repository";

export interface CommitResult {
  sha: string;
  branch: string;
  title: string;
}

// Shape returned by the backend commit-list endpoint.
interface CommitOut {
  sha: string;
  title: string;
  description: string;
  author: string;
  date: string;
}

// List a project's commits, newest first. The backend doesn't tag each commit
// with its branch yet, so we label them with the branch being viewed.
export async function listCommits(
  projectId: number,
  branch: string,
): Promise<Commit[]> {
  const commits = await apiFetch<CommitOut[]>(
    `/projects/${projectId}/commits?branch=${encodeURIComponent(branch)}`,
  );
  return commits.map((c) => ({
    hash: c.sha.slice(0, 7),
    sha: c.sha,
    message: c.title,
    author: c.author,
    branch,
    at: c.date,
  }));
}

// A branch plus its latest commit and its position relative to the default
// branch (ahead/behind), as the branches endpoint reports them.
export interface BranchSummary {
  name: string;
  isDefault: boolean;
  isProtected: boolean;
  ahead: number;
  behind: number;
  lastCommitHash?: string;
  lastCommitSha?: string;
  lastCommitMessage?: string;
  lastCommitAuthor?: string;
  lastCommitAt?: string;
}

// What the backend returns per branch: enriched with its tip commit and
// default/protected flags (see backend README, GET /branches).
interface BranchOut {
  name: string;
  is_default: boolean;
  is_protected: boolean;
  latest_commit: CommitOut | null;
  ahead: number;
  behind: number;
  merged: boolean;
}

// List a project's branches, each with its newest commit. The branches endpoint
// already embeds the tip commit, so this is a single request.
export async function listBranches(
  projectId: number,
): Promise<BranchSummary[]> {
  const branches = await apiFetch<BranchOut[]>(
    `/projects/${projectId}/branches`,
  );
  return branches.map((b) => ({
    name: b.name,
    isDefault: b.is_default,
    isProtected: b.is_protected,
    ahead: b.ahead,
    behind: b.behind,
    lastCommitHash: b.latest_commit?.sha.slice(0, 7),
    lastCommitSha: b.latest_commit?.sha,
    lastCommitMessage: b.latest_commit?.title,
    lastCommitAuthor: b.latest_commit?.author,
    lastCommitAt: b.latest_commit?.date,
  }));
}

// Create a branch off a start point (default main). Returns the project's
// updated branch list.
export function createBranch(
  projectId: number,
  name: string,
  startPoint = "main",
): Promise<string[]> {
  return apiFetch<string[]>(`/projects/${projectId}/branches`, {
    method: "POST",
    json: { name, start_point: startPoint },
  });
}

// Commit one or more files to a branch as a single commit.
//
// Each file is appended under the `files` field of one multipart request, along
// with the branch, the title (commit message) and an optional description. The
// backend accepts repeated `files` entries so the whole set lands as one commit.
export async function commitFiles(
  projectId: number,
  input: {
    branch: string;
    message: string;
    description?: string;
    files: File[];
  },
): Promise<CommitResult> {
  const body = new FormData();
  body.append("branch", input.branch);
  body.append("title", input.message);
  body.append("description", input.description ?? "");
  for (const file of input.files) body.append("files", file, file.name);

  return apiFetch<CommitResult>(`/projects/${projectId}/commits`, {
    method: "POST",
    formData: body,
  });
}
