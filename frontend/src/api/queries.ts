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
  getMergeRequest,
  listChangeRequests,
  type ChangeRequestSummary,
  type MergeRequest,
} from "./mergeRequest";
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
  changeRequests: (projectId: number) =>
    ["projects", projectId, "pulls"] as const,
  mergeRequest: (slug: string, mrId: string) =>
    ["merge-request", slug, mrId] as const,
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
