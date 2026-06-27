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

// A branch plus its latest commit. The backend doesn't expose branch
// comparison, so there's no ahead/behind here.
export interface BranchSummary {
  name: string;
  isDefault: boolean;
  lastCommitHash?: string;
  lastCommitSha?: string;
  lastCommitMessage?: string;
  lastCommitAuthor?: string;
  lastCommitAt?: string;
}

// List a project's branches, each with its newest commit. The branches
// endpoint returns names only, so we fetch the latest commit per branch to
// fill in the rest.
export async function listBranches(
  projectId: number,
): Promise<BranchSummary[]> {
  const names = await apiFetch<string[]>(`/projects/${projectId}/branches`);
  return Promise.all(
    names.map(async (name) => {
      let latest: CommitOut | undefined;
      try {
        const commits = await apiFetch<CommitOut[]>(
          `/projects/${projectId}/commits?branch=${encodeURIComponent(name)}`,
        );
        latest = commits[0];
      } catch {
        latest = undefined;
      }
      return {
        name,
        isDefault: name === "main",
        lastCommitHash: latest?.sha.slice(0, 7),
        lastCommitSha: latest?.sha,
        lastCommitMessage: latest?.title,
        lastCommitAuthor: latest?.author,
        lastCommitAt: latest?.date,
      };
    }),
  );
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
// Each file is appended under the `file` field of one multipart request, along
// with the branch, the title (commit message) and an optional description. A
// single file matches the current backend route; the multi-file endpoint being
// added accepts repeated `file` entries so the whole set lands as one commit.
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
  for (const file of input.files) body.append("file", file, file.name);

  return apiFetch<CommitResult>(`/projects/${projectId}/commits`, {
    method: "POST",
    formData: body,
  });
}
