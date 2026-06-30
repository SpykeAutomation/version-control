import { apiFetch } from "./client";
import { displayName, type UserBrief } from "./users";

export interface Project {
  id: number;
  name: string;
  slug: string;
  owner_id: number;
  created_at: string;
  branches: string[];
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
