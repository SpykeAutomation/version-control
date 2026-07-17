import { apiFetch, ApiError } from "./client";
import { displayName, type UserBrief } from "./users";

export interface Project {
  id: number;
  name: string;
  slug: string;
  owner_id: number;
  created_at: string;
  branches: string[];
  // The caller's role on this project ("owner" | "admin" | "member"), echoed
  // by the backend so the UI can hide controls the user can't use.
  your_role?: string;
}

export type RepoStatus = "production" | "commissioning" | "review" | "draft";

// View model for the Projects table. The extra fields aren't in the backend
// contract yet, so they're optional: absent (and shown as "—") until those
// endpoints exist.
export interface ProjectRow extends Project {
  controller?: string;
  controller_model?: string; // CPU / model, shown under the controller name
  description?: string; // one-line repository description
  status?: RepoStatus;
  latest_release?: string;
  latest_release_at?: string; // ISO date of the latest release
  owner?: string; // display name of the repository owner
  updated_at?: string;
  last_activity_by?: string;
  open_changes?: number;
  recent_commits?: number; // recent commit count, shown in the activity cell
  activity?: number[];
}

export interface Member {
  id: number;
  email: string;
  name: string;
  role: string;
}

// What the backend actually sends for a project: `owner` is a nested user
// object, not a display string. Map it into the flat ProjectRow the table wants.
interface ProjectApi {
  id: number;
  name: string;
  slug: string;
  description?: string;
  owner: UserBrief;
  created_at: string;
  branches: string[];
  your_role?: string;
}

export function createProject(name: string): Promise<Project> {
  return apiFetch<Project>("/projects", { method: "POST", json: { name } });
}

export async function listProjects(): Promise<ProjectRow[]> {
  const rows = await apiFetch<ProjectApi[]>("/projects");
  return rows.map((p) => ({
    ...p,
    owner_id: p.owner.id,
    owner: displayName(p.owner),
    description: p.description || undefined,
  }));
}

// The backend Member is {id, email, first_name, last_name, role}; the table
// wants a single display name.
interface MemberApi {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
  role: string;
}

export async function listMembers(projectId: number): Promise<Member[]> {
  const rows = await apiFetch<MemberApi[]>(`/projects/${projectId}/members`);
  return rows.map((m) => ({
    id: m.id,
    email: m.email,
    name: displayName(m),
    role: m.role,
  }));
}

// A same-org, non-member account matching a search fragment — the add-member
// typeahead's row. Served by GET /member-candidates (backend addition; until
// it is deployed the endpoint 404s and the UI falls back to exact-email add).
export interface MemberCandidate {
  id: number;
  email: string;
  name: string;
}

export async function searchMemberCandidates(
  projectId: number,
  q: string,
): Promise<MemberCandidate[]> {
  // Backend MemberCandidate: {id, email, first_name, last_name, avatar}.
  const rows = await apiFetch<
    { id: number; email: string; first_name?: string; last_name?: string }[]
  >(`/projects/${projectId}/member-candidates?q=${encodeURIComponent(q)}`);
  return rows.map((m) => ({ id: m.id, email: m.email, name: displayName(m) }));
}

// Add a member by email. The backend resolves the account (404 if unknown).
export function addMember(
  projectId: number,
  email: string,
  role: "member" | "admin" = "member",
): Promise<unknown> {
  return apiFetch(`/projects/${projectId}/members`, {
    method: "POST",
    json: { email, role },
  });
}

export function updateMemberRole(
  projectId: number,
  userId: number,
  role: "member" | "admin",
): Promise<unknown> {
  return apiFetch(`/projects/${projectId}/members/${userId}`, {
    method: "PATCH",
    json: { role },
  });
}

export function removeMember(
  projectId: number,
  userId: number,
): Promise<void> {
  return apiFetch(`/projects/${projectId}/members/${userId}`, {
    method: "DELETE",
  });
}

// Transfer ownership (current owner only). The previous owner is demoted to
// admin by the backend.
export function transferOwnership(
  projectId: number,
  newOwnerId: number,
): Promise<unknown> {
  return apiFetch(`/projects/${projectId}/transfer`, {
    method: "POST",
    json: { new_owner_id: newOwnerId },
  });
}

// Delete the repository and everything attached to it (owner/admin).
export function deleteProject(projectId: number): Promise<void> {
  return apiFetch(`/projects/${projectId}`, { method: "DELETE" });
}

// Change the project's default branch (owner only). The backend feature may
// not be deployed yet: production's PATCH ignores unknown fields and answers
// 200 without applying, so success is only believed when the response echoes
// the new default back — anything else surfaces as an error, never as a
// silent false success.
export async function setDefaultBranch(
  projectId: number,
  branch: string,
): Promise<void> {
  const res = await apiFetch<{ default_branch?: string }>(
    `/projects/${projectId}`,
    { method: "PATCH", json: { default_branch: branch } },
  );
  if (res.default_branch !== branch) {
    throw new ApiError(
      501,
      "The backend doesn't support changing the default branch yet — nothing was changed.",
    );
  }
}

// The slice of GET /projects/{id}/overview the org home aggregates: the
// controller inside the repo's L5X and its open merge-request count. The
// list endpoint doesn't carry these (yet — a backend change folds them in);
// until then the home page fans out one overview call per repo.
export interface ProjectOverviewBrief {
  controller_name: string | null;
  open_pull_count: number;
}

export function getProjectOverview(
  projectId: number,
): Promise<ProjectOverviewBrief> {
  return apiFetch<ProjectOverviewBrief>(`/projects/${projectId}/overview`);
}
