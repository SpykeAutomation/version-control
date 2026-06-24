import { apiFetch } from "./client";
import { DEMO, demoProject } from "../demo";

export interface Project {
  id: number;
  name: string;
  slug: string;
  owner_id: number;
  created_at: string;
  branches: string[];
}

export function createProject(name: string): Promise<Project> {
  if (DEMO) return Promise.resolve({ ...demoProject, name, slug: name });
  return apiFetch<Project>("/projects", { method: "POST", json: { name } });
}

export function listProjects(): Promise<Project[]> {
  if (DEMO) return Promise.resolve([demoProject]);
  return apiFetch<Project[]>("/projects");
}
