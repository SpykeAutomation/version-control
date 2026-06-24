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
// contract yet, so they're optional: populated in demo mode, absent (and shown
// as "—") against the real API until those endpoints exist.
export interface ProjectRow extends Project {
  controller?: string;
  status?: RepoStatus;
  latest_release?: string;
  updated_at?: string;
  last_activity_by?: string;
  open_changes?: number;
  activity?: number[];
}

export function createProject(name: string): Promise<Project> {
  return apiFetch<Project>("/projects", { method: "POST", json: { name } });
}

export function listProjects(): Promise<ProjectRow[]> {
  return apiFetch<ProjectRow[]>("/projects");
}
