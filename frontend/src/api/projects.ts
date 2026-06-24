import { apiFetch } from "./client";
import { DEMO, demoProject, demoProjects } from "../demo";

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
  if (DEMO) return Promise.resolve({ ...demoProject, name, slug: name });
  return apiFetch<Project>("/projects", { method: "POST", json: { name } });
}

export function listProjects(): Promise<ProjectRow[]> {
  if (DEMO) return Promise.resolve(demoProjects);
  return apiFetch<ProjectRow[]>("/projects");
}
