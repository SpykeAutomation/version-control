import { apiFetch } from "./client";
import type { Commit } from "./repository";
import { shortSha } from "../lib/format";

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
  files_changed?: number;
  parents?: string[]; // first parent first; empty for a root commit
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
    hash: shortSha(c.sha),
    sha: c.sha,
    message: c.title,
    author: c.author,
    branch,
    at: c.date,
    filesChanged: c.files_changed,
    parents: c.parents ?? [],
  }));
}

// A branch plus its latest commit and its position relative to the default
// branch (ahead/behind), as the branches endpoint reports them.
export interface BranchSummary {
  name: string;
  isDefault: boolean;
  isProtected: boolean;
  requiredApprovals: number; // approvals a PR into this branch needs to merge
  merged: boolean; // fully merged into the default branch (ahead == 0)
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
  required_approvals?: number;
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
    requiredApprovals: b.required_approvals ?? 0,
    merged: b.merged,
    ahead: b.ahead,
    behind: b.behind,
    lastCommitHash: b.latest_commit ? shortSha(b.latest_commit.sha) : undefined,
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

// Restore an earlier commit's repo state as ONE new commit on the branch
// (history preserved — nothing is rewritten). The backend re-checks that
// `expectedTipSha` is still the branch tip inside its write lock and answers
// 409 (current tip in `detail`) when the branch has moved; 403 for a plain
// member on a protected branch; 400 for a target that is already the tip,
// isn't an ancestor, or whose tree matches the tip's.
export function revertBranch(
  projectId: number,
  input: {
    branch: string;
    targetSha: string;
    expectedTipSha: string;
    message?: string;
  },
): Promise<CommitResult> {
  return apiFetch<CommitResult>(`/projects/${projectId}/revert`, {
    method: "POST",
    json: {
      branch: input.branch,
      target_sha: input.targetSha,
      expected_tip_sha: input.expectedTipSha,
      ...(input.message ? { message: input.message } : {}),
    },
  });
}

// Protect or unprotect a branch, setting how many PR approvals a merge into it
// needs. Owner/admin; the backend rejects unprotecting the default branch.
export function setBranchProtection(
  projectId: number,
  branch: string,
  isProtected: boolean,
  requiredApprovals = 0,
): Promise<unknown> {
  return apiFetch(
    `/projects/${projectId}/branches/${encodeURIComponent(branch)}/protection`,
    {
      method: "PUT",
      json: { protected: isProtected, required_approvals: requiredApprovals },
    },
  );
}
