// React Query hooks over the raw API functions. Components use these instead of
// fetching in useEffect, so results are cached and shared: the project list is
// fetched once and reused across every page, and revisiting a page renders from
// cache instead of reloading.

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "./client";
import {
  createProject,
  listMembers,
  listProjects,
  type Project,
  type ProjectRow,
} from "./projects";
import { listBranches, listCommits, type BranchSummary } from "./commits";
import {
  getCommitDiff,
  getCommitLadderDiff,
  getDiff,
  getLadderDiff,
  type ChangeSet,
  type LadderDiffDoc,
} from "./diff";
import {
  getCommitTree,
  getTree,
  type ProjectTree,
} from "./tree";
import {
  createComment,
  getMergeRequest,
  listChangeRequests,
  type ChangeRequestSummary,
  type MergeRequest,
} from "./mergeRequest";
import { getCommit, type CommitDetail } from "./commit";
import type { Commit } from "./repository";

// Cache keys. Everything for a project is nested under ["projects", id] so a
// single invalidation after a write refreshes that project's commits,
// branches, members and change requests together.
export const queryKeys = {
  projects: ["projects"] as const,
  members: (projectId: number) => ["projects", projectId, "members"] as const,
  commits: (projectId: number, branch: string) =>
    ["projects", projectId, "commits", branch] as const,
  branches: (projectId: number) => ["projects", projectId, "branches"] as const,
  commitDiff: (projectId: number, sha: string) =>
    ["projects", projectId, "commit-diff", sha] as const,
  commitLadderDiff: (projectId: number, sha: string) =>
    ["projects", projectId, "commit-ladder", sha] as const,
  diff: (projectId: number, base: string, head: string) =>
    ["projects", projectId, "diff", base, head] as const,
  ladderDiff: (projectId: number, base: string, head: string) =>
    ["projects", projectId, "ladder-diff", base, head] as const,
  commitTree: (projectId: number, sha: string) =>
    ["projects", projectId, "commit-tree", sha] as const,
  tree: (projectId: number, base: string, head: string) =>
    ["projects", projectId, "tree", base, head] as const,
  changeRequests: (projectId: number) =>
    ["projects", projectId, "pulls"] as const,
  mergeRequest: (slug: string, mrId: string) =>
    ["merge-request", slug, mrId] as const,
  commit: (slug: string, sha: string) => ["commit-detail", slug, sha] as const,
};

// Turn a query error into a message, falling back when it isn't an ApiError.
export function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function useProjects() {
  return useQuery({ queryKey: queryKeys.projects, queryFn: listProjects });
}

// The project list plus the one matching `slug`. Most pages need a single
// project but the backend only lists them all, so we derive it here.
export function useProject(slug: string | undefined) {
  const query = useProjects();
  const project = useMemo<ProjectRow | null>(
    () => query.data?.find((p) => p.slug === slug) ?? null,
    [query.data, slug],
  );
  return { ...query, project };
}

export function useMembers(projectId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.members(projectId ?? -1),
    queryFn: () => listMembers(projectId!),
    enabled: projectId != null,
  });
}

export function useCommits(projectId: number | undefined, branch: string) {
  return useQuery<Commit[]>({
    queryKey: queryKeys.commits(projectId ?? -1, branch),
    queryFn: () => listCommits(projectId!, branch),
    enabled: projectId != null,
  });
}

export function useBranches(projectId: number | undefined) {
  return useQuery<BranchSummary[]>({
    queryKey: queryKeys.branches(projectId ?? -1),
    queryFn: () => listBranches(projectId!),
    enabled: projectId != null,
  });
}

// The semantic change-set for one commit. Needs both the project and a commit
// sha, so it stays disabled until both are known.
export function useCommitDiff(
  projectId: number | undefined,
  sha: string | undefined,
) {
  return useQuery<ChangeSet>({
    queryKey: queryKeys.commitDiff(projectId ?? -1, sha ?? ""),
    queryFn: () => getCommitDiff(projectId!, sha!),
    enabled: projectId != null && !!sha,
  });
}

// The ladder-diff IR for one commit, used by the rung-by-rung panels.
export function useCommitLadderDiff(
  projectId: number | undefined,
  sha: string | undefined,
) {
  return useQuery<LadderDiffDoc>({
    queryKey: queryKeys.commitLadderDiff(projectId ?? -1, sha ?? ""),
    queryFn: () => getCommitLadderDiff(projectId!, sha!),
    enabled: projectId != null && !!sha,
  });
}

// Generic diff between two refs, used when the commit page compares against a
// base other than the parent. Disabled until both refs are known.
export function useDiff(
  projectId: number | undefined,
  base: string | undefined,
  head: string | undefined,
) {
  return useQuery<ChangeSet>({
    queryKey: queryKeys.diff(projectId ?? -1, base ?? "", head ?? ""),
    queryFn: () => getDiff(projectId!, base!, head!),
    enabled: projectId != null && !!base && !!head,
  });
}

export function useLadderDiff(
  projectId: number | undefined,
  base: string | undefined,
  head: string | undefined,
) {
  return useQuery<LadderDiffDoc>({
    queryKey: queryKeys.ladderDiff(projectId ?? -1, base ?? "", head ?? ""),
    queryFn: () => getLadderDiff(projectId!, base!, head!),
    enabled: projectId != null && !!base && !!head,
  });
}

// The organizer tree for one commit (full structure + change status). Mirrors
// useCommitDiff's gating: disabled until both the project and sha are known.
export function useCommitTree(
  projectId: number | undefined,
  sha: string | undefined,
) {
  return useQuery<ProjectTree>({
    queryKey: queryKeys.commitTree(projectId ?? -1, sha ?? ""),
    queryFn: () => getCommitTree(projectId!, sha!),
    enabled: projectId != null && !!sha,
  });
}

// The organizer tree at a custom base, used when the commit page compares
// against a base other than the parent. Disabled until both refs are known.
export function useTree(
  projectId: number | undefined,
  base: string | undefined,
  head: string | undefined,
) {
  return useQuery<ProjectTree>({
    queryKey: queryKeys.tree(projectId ?? -1, base ?? "", head ?? ""),
    queryFn: () => getTree(projectId!, base!, head!),
    enabled: projectId != null && !!base && !!head,
  });
}

export function useChangeRequests(projectId: number | undefined) {
  return useQuery<ChangeRequestSummary[]>({
    queryKey: queryKeys.changeRequests(projectId ?? -1),
    queryFn: () => listChangeRequests(projectId!),
    enabled: projectId != null,
  });
}

export function useMergeRequest(
  slug: string | undefined,
  mrId: string | undefined,
) {
  return useQuery<MergeRequest>({
    queryKey: queryKeys.mergeRequest(slug ?? "", mrId ?? ""),
    queryFn: () => getMergeRequest(slug!, mrId!),
    enabled: !!slug && !!mrId,
  });
}

// One commit's review detail (meta, grouped diffs, discussion). Falls back to
// demo data inside getCommit when the backend is unreachable.
export function useCommit(
  slug: string | undefined,
  sha: string | undefined,
) {
  return useQuery<CommitDetail>({
    queryKey: queryKeys.commit(slug ?? "", sha ?? ""),
    queryFn: () => getCommit(slug!, sha!),
    enabled: !!slug && !!sha,
  });
}

// Posting a comment adds to a merge request's thread, so refresh that merge
// request on success to pull in the new comment.
export function useCreateComment(
  slug: string | undefined,
  mrId: string | undefined,
) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, string>({
    mutationFn: (body) => createComment(slug!, mrId!, body),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: queryKeys.mergeRequest(slug ?? "", mrId ?? ""),
      });
    },
  });
}

// Creating a project changes the cached list, so refresh it on success.
export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation<Project, Error, string>({
    mutationFn: (name) => createProject(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects });
    },
  });
}
