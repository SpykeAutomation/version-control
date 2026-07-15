// React Query hooks over the raw API functions. Components use these instead of
// fetching in useEffect, so results are cached and shared: the project list is
// fetched once and reused across every page, and revisiting a page renders from
// cache instead of reloading.

import { useMemo } from "react";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ApiError } from "./client";
import {
  addMember,
  createProject,
  deleteProject,
  listMembers,
  listProjects,
  removeMember,
  searchMemberCandidates,
  transferOwnership,
  updateMemberRole,
  type MemberCandidate,
  type Project,
  type ProjectRow,
} from "./projects";
import {
  listBranches,
  listCommits,
  setBranchProtection,
  type BranchSummary,
} from "./commits";
import { listProjectFiles } from "./files";
import type { FileEntry } from "./repository";
import {
  getCommitDiff,
  getCommitLadderDiff,
  getCommitTextDiff,
  getDiff,
  getLadderDiff,
  type ChangeSet,
  type LadderDiffDoc,
  type TextDiff,
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
  mergeChangeRequest,
  type ChangeRequestSummary,
  type MergeOutcome,
  type MergeRequest,
} from "./mergeRequest";
import {
  getCommit,
  getRoutineContent,
  type CommitDetail,
  type RoutineFull,
} from "./commit";
import {
  getL5xAoi,
  getL5xController,
  getL5xDataTypes,
  getL5xModules,
  getL5xTags,
  type L5XAoi,
  type L5XController,
  type L5XDataType,
  type L5XModule,
  type L5XTag,
} from "./l5x";
import { getCompareView, type CompareView } from "./compare";
import {
  addCommitComment,
  listCommitComments,
  type CommitComment,
} from "./comments";
import { mapRepository, type Commit } from "./repository";

// Cache keys. Everything for a project is nested under ["projects", id] so a
// single invalidation after a write refreshes that project's commits,
// branches, members and change requests together.
export const queryKeys = {
  projects: ["projects"] as const,
  members: (projectId: number) => ["projects", projectId, "members"] as const,
  commits: (projectId: number, branch: string) =>
    ["projects", projectId, "commits", branch] as const,
  branches: (projectId: number) => ["projects", projectId, "branches"] as const,
  files: (projectId: number, ref: string) =>
    ["projects", projectId, "files", ref] as const,
  commitDiff: (projectId: number, sha: string) =>
    ["projects", projectId, "commit-diff", sha] as const,
  commitLadderDiff: (projectId: number, sha: string) =>
    ["projects", projectId, "commit-ladder", sha] as const,
  commitTextDiff: (projectId: number, sha: string, path: string) =>
    ["projects", projectId, "commit-text-diff", sha, path] as const,
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
  repository: (slug: string) => ["repository", slug] as const,
  routineContent: (projectId: number, sha: string, program: string, routine: string) =>
    ["projects", projectId, "commit-routine", sha, program, routine] as const,
  l5xSection: (projectId: number, ref: string, path: string, section: string, name: string) =>
    ["projects", projectId, "l5x", ref, path, section, name] as const,
  compareView: (projectId: number, base: string, head: string) =>
    ["projects", projectId, "compare", base, head] as const,
  commitComments: (projectId: number, sha: string) =>
    ["projects", projectId, "commit-comments", sha] as const,
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

// ---- Settings tab: members, protection, ownership ----

// Live add-member search (backend addition; 404 until deployed — the settings
// tab catches that and falls back to exact-email add). Debounce in the caller.
export function useMemberCandidates(
  projectId: number | undefined,
  q: string,
) {
  return useQuery<MemberCandidate[]>({
    queryKey: ["projects", projectId ?? -1, "member-candidates", q],
    queryFn: () => searchMemberCandidates(projectId!, q),
    enabled: projectId != null && q.trim().length >= 2,
    staleTime: 30_000,
    retry: false, // a 404 (endpoint not deployed) should fail fast, not retry
  });
}

export function useAddMember(projectId: number | undefined) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { email: string; role?: "member" | "admin" }>({
    mutationFn: (input) => addMember(projectId!, input.email, input.role),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.members(projectId ?? -1) });
    },
  });
}

export function useUpdateMemberRole(projectId: number | undefined) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { userId: number; role: "member" | "admin" }>({
    mutationFn: (input) => updateMemberRole(projectId!, input.userId, input.role),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.members(projectId ?? -1) });
    },
  });
}

export function useRemoveMember(projectId: number | undefined) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, number>({
    mutationFn: (userId) => removeMember(projectId!, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.members(projectId ?? -1) });
    },
  });
}

// Transferring ownership changes roles (old owner -> admin), which the project
// list echoes via your_role — refresh both.
export function useTransferOwnership(projectId: number | undefined) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, number>({
    mutationFn: (newOwnerId) => transferOwnership(projectId!, newOwnerId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.members(projectId ?? -1) });
      qc.invalidateQueries({ queryKey: queryKeys.projects });
    },
  });
}

export function useDeleteProject(projectId: number | undefined) {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => deleteProject(projectId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects });
    },
  });
}

export function useSetBranchProtection(projectId: number | undefined) {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { branch: string; isProtected: boolean; requiredApprovals?: number }
  >({
    mutationFn: (input) =>
      setBranchProtection(
        projectId!,
        input.branch,
        input.isProtected,
        input.requiredApprovals ?? 0,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.branches(projectId ?? -1) });
    },
  });
}

// The project's files at a ref (branch or commit). Disabled until both the
// project and ref are known.
export function useProjectFiles(
  projectId: number | undefined,
  ref: string | undefined,
) {
  return useQuery<FileEntry[]>({
    queryKey: queryKeys.files(projectId ?? -1, ref ?? ""),
    queryFn: () => listProjectFiles(projectId!, ref!),
    enabled: projectId != null && !!ref,
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

// The text diff for one non-L5X file at a commit, fetched lazily by the
// Changes tab's per-file sections.
export function useCommitTextDiff(
  projectId: number | undefined,
  sha: string | undefined,
  path: string,
) {
  return useQuery<TextDiff>({
    queryKey: queryKeys.commitTextDiff(projectId ?? -1, sha ?? "", path),
    queryFn: () => getCommitTextDiff(projectId!, sha!, path),
    enabled: projectId != null && !!sha && !!path,
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

// Merged pulls, used by the commit graph to attribute "Merge pull request #N"
// trunk commits to the branch they brought in.
export function useMergedPulls(projectId: number | undefined) {
  return useQuery<ChangeRequestSummary[]>({
    queryKey: [...queryKeys.changeRequests(projectId ?? -1), "merged"],
    queryFn: () => listChangeRequests(projectId!, "merged"),
    enabled: projectId != null,
  });
}

// Every branch's commit list at once (one request per branch, cached under
// the same keys the per-branch views use). Drives the commit graph.
export function useAllBranchCommits(
  projectId: number | undefined,
  branchNames: string[],
) {
  return useQueries({
    queries: branchNames.map((b) => ({
      queryKey: queryKeys.commits(projectId ?? -1, b),
      queryFn: () => listCommits(projectId!, b),
      enabled: projectId != null,
    })),
    combine: (results) => ({
      isPending: results.some((r) => r.isPending),
      error: results.find((r) => r.error)?.error ?? null,
      byBranch: Object.fromEntries(
        branchNames.map((b, i) => [b, results[i]?.data ?? null]),
      ) as Record<string, Commit[] | null>,
    }),
  });
}

// The project is read from the shared project-list cache (via useProject), so
// these detail hooks pass its id straight through instead of re-listing every
// project on each detail load. React Query dedupes the underlying list query, so
// calling useProject here on top of the page's own call costs no extra request.
export function useMergeRequest(
  slug: string | undefined,
  mrId: string | undefined,
) {
  const { project } = useProject(slug);
  return useQuery<MergeRequest>({
    queryKey: queryKeys.mergeRequest(slug ?? "", mrId ?? ""),
    queryFn: () => getMergeRequest(project!.id, mrId!),
    enabled: !!slug && !!mrId && project != null,
  });
}

// One commit's review detail (meta, grouped diffs, discussion).
export function useCommit(
  slug: string | undefined,
  sha: string | undefined,
) {
  const { project } = useProject(slug);
  return useQuery<CommitDetail>({
    queryKey: queryKeys.commit(slug ?? "", sha ?? ""),
    queryFn: () => getCommit(project!.id, project!.branches, sha!),
    enabled: !!slug && !!sha && project != null,
  });
}

// One repository's rich detail (controller, tags, linked controller). Derived
// entirely from the cached project row — the backend has no detail endpoint — so
// this maps client-side rather than firing another request.
export function useRepository(slug: string | undefined) {
  const { project, ...rest } = useProject(slug);
  const data = useMemo(
    () => (project ? mapRepository(project) : undefined),
    [project],
  );
  return { ...rest, project, data };
}

// One routine's full content at a commit, for the Files tab. Disabled unless
// all keys are known and `enabled` is set (the caller skips it when the content
// is already loaded). No retry: a missing backend endpoint should fall back to
// the placeholder quickly, not hammer.
export function useRoutineContent(
  projectId: number | undefined,
  sha: string | undefined,
  program: string | undefined,
  routine: string | undefined,
  enabled: boolean,
) {
  return useQuery<RoutineFull>({
    queryKey: queryKeys.routineContent(
      projectId ?? -1,
      sha ?? "",
      program ?? "",
      routine ?? "",
    ),
    queryFn: () => getRoutineContent(projectId!, sha!, program!, routine!),
    enabled: enabled && projectId != null && !!sha && !!program && !!routine,
    retry: false,
  });
}

// --- L5X sections: the data behind the organizer's detail panels. A section
// is a pure function of (ref, file), and the commit page always passes a
// commit sha, so results never go stale — cache them for the session.
function useL5x<T>(
  section: string,
  fetch: (projectId: number, ref: string, path: string) => Promise<T>,
  projectId: number | undefined,
  ref: string | undefined,
  path: string | null | undefined,
  name = "",
) {
  return useQuery<T>({
    queryKey: queryKeys.l5xSection(
      projectId ?? -1,
      ref ?? "",
      path ?? "",
      section,
      name,
    ),
    queryFn: () => fetch(projectId!, ref!, path!),
    enabled: projectId != null && !!ref && !!path,
    staleTime: Infinity,
    retry: false,
  });
}

export function useL5xDataTypes(
  projectId: number | undefined,
  ref: string | undefined,
  path: string | null | undefined,
) {
  return useL5x<L5XDataType[]>("datatypes", getL5xDataTypes, projectId, ref, path);
}

export function useL5xTags(
  projectId: number | undefined,
  ref: string | undefined,
  path: string | null | undefined,
) {
  return useL5x<L5XTag[]>("tags", getL5xTags, projectId, ref, path);
}

export function useL5xModules(
  projectId: number | undefined,
  ref: string | undefined,
  path: string | null | undefined,
) {
  return useL5x<L5XModule[]>("modules", getL5xModules, projectId, ref, path);
}

// The controller identity of one L5X file (name, processor, revision) —
// shown beside the file in listings. Callers pass a BRANCH as the ref, so
// unlike the sha-keyed hooks above this one uses the default staleness and
// refetches when the branch moves.
export function useL5xController(
  projectId: number | undefined,
  ref: string | undefined,
  path: string | null | undefined,
) {
  return useQuery<L5XController>({
    queryKey: queryKeys.l5xSection(
      projectId ?? -1,
      ref ?? "",
      path ?? "",
      "controller",
      "",
    ),
    queryFn: () => getL5xController(projectId!, ref!, path!),
    enabled: projectId != null && !!ref && !!path,
    retry: false,
  });
}

export function useL5xAoi(
  projectId: number | undefined,
  ref: string | undefined,
  path: string | null | undefined,
  name: string | undefined,
) {
  return useL5x<L5XAoi>(
    "aoi",
    (id, r, p) => getL5xAoi(id, r, p, name!),
    projectId,
    ref,
    name ? path : undefined,
    name ?? "",
  );
}

// Rolled-up compare summary + per-file impact rows for a ref pair. Used by
// the revert preview (base = current tip, head = revert target).
export function useCompareView(
  projectId: number | undefined,
  base: string | undefined,
  head: string | undefined,
) {
  return useQuery<CompareView>({
    queryKey: queryKeys.compareView(projectId ?? -1, base ?? "", head ?? ""),
    queryFn: () => getCompareView(projectId!, base!, head!),
    enabled: projectId != null && !!base && !!head,
  });
}

// The commit page's persistent discussion (flat list; the page nests by
// parentId). Comments are mutable (people keep posting), so no staleTime.
export function useCommitComments(
  projectId: number | undefined,
  sha: string | undefined,
) {
  return useQuery<CommitComment[]>({
    queryKey: queryKeys.commitComments(projectId ?? -1, sha ?? ""),
    queryFn: () => listCommitComments(projectId!, sha!),
    enabled: projectId != null && !!sha,
  });
}

// Posting refreshes the commit's comment list.
export function useAddCommitComment(
  projectId: number | undefined,
  sha: string | undefined,
) {
  const qc = useQueryClient();
  return useMutation<CommitComment, Error, { body: string; parentId?: number | null }>({
    mutationFn: (input) => addCommitComment(projectId!, sha!, input),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: queryKeys.commitComments(projectId ?? -1, sha ?? ""),
      });
    },
  });
}

// Posting a comment adds to a merge request's thread, so refresh that merge
// request on success to pull in the new comment.
export function useCreateComment(
  slug: string | undefined,
  mrId: string | undefined,
) {
  const qc = useQueryClient();
  const { project } = useProject(slug);
  return useMutation<unknown, Error, { body: string; parentId?: number | null }>({
    mutationFn: (input) => createComment(project!.id, mrId!, input),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: queryKeys.mergeRequest(slug ?? "", mrId ?? ""),
      });
    },
  });
}

// Merging a change request lands the source branch on its target, so refresh
// both this merge request and the project's data (commits, branches, requests).
// Only meaningful when projectId is known; callers thread it through.
export function useMergePull(
  slug: string | undefined,
  mrId: string | undefined,
  projectId: number | undefined,
) {
  const qc = useQueryClient();
  // Derive the numeric pull number from the id's digits, as mergeRequest.ts does.
  const match = (mrId ?? "").match(/\d+/);
  const number = match ? parseInt(match[0], 10) : NaN;
  return useMutation<MergeOutcome, Error, void>({
    mutationFn: () => mergeChangeRequest(projectId!, number),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: queryKeys.mergeRequest(slug ?? "", mrId ?? ""),
      });
      qc.invalidateQueries({ queryKey: ["projects", projectId] });
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
