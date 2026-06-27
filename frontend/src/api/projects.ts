import { apiFetch } from "./client";

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

export function createProject(name: string): Promise<Project> {
  return apiFetch<Project>("/projects", { method: "POST", json: { name } });
}

export async function listProjects(): Promise<ProjectRow[]> {
  return apiFetch<ProjectRow[]>("/projects");
}

export function listMembers(projectId: number): Promise<Member[]> {
  return apiFetch<Member[]>(`/projects/${projectId}/members`);
}
