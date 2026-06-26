import { apiFetch, ApiError } from "./client";

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
  try {
    return await apiFetch<ProjectRow[]>("/projects");
  } catch (err) {
    // A status-0 ApiError means the server is unreachable (e.g. no backend in
    // local dev) — show sample repositories rather than an error banner.
    if (err instanceof ApiError && err.status === 0) return demoProjects();
    throw err;
  }
}

export function listMembers(projectId: number): Promise<Member[]> {
  return apiFetch<Member[]>(`/projects/${projectId}/members`);
}

// --- Demo data ---
// A fully populated, synthetic set of repositories used when no backend is
// reachable. Everything here is invented sample content, not derived from any
// real file.
export function demoProjects(): ProjectRow[] {
  const now = Date.now();
  const ago = (minutes: number) =>
    new Date(now - minutes * 60_000).toISOString();

  return [
    {
      id: 1,
      name: "Packaging Line 3",
      slug: "packaging-line-3",
      owner_id: 1,
      created_at: "2025-09-12T09:00:00.000Z",
      branches: ["main", "feature/case-sealer", "fix/jam-detect"],
      description: "Carton loader, case packing, and case sealing control",
      controller: "Siemens S7-1500",
      controller_model: "CPU 1516-3 PN/DP",
      status: "production",
      latest_release: "v2.14.0",
      latest_release_at: "2026-06-17T00:00:00.000Z",
      owner: "Alex Morgan",
      updated_at: ago(120),                  // 2 hours ago
      last_activity_by: "Alex Morgan",
      open_changes: 3,
      recent_commits: 2,
    },
    {
      id: 2,
      name: "Palletizer Cell A",
      slug: "palletizer-cell-a",
      owner_id: 1,
      created_at: "2025-10-02T09:00:00.000Z",
      branches: ["main", "feature/safety-mat"],
      description: "Palletizing cell with safety, interlocks, and HMI",
      controller: "Allen-Bradley",
      controller_model: "ControlLogix 5580",
      status: "commissioning",
      latest_release: "v1.8.3",
      latest_release_at: "2026-06-03T00:00:00.000Z",
      owner: "Priya Nair",
      updated_at: ago(60 * 24 * 3),          // 3 days ago
      last_activity_by: "Jamie Davis",
      open_changes: 2,
      recent_commits: 1,
    },
    {
      id: 3,
      name: "CIP Skid 02",
      slug: "cip-skid-02",
      owner_id: 1,
      created_at: "2025-11-18T09:00:00.000Z",
      branches: ["develop", "main", "feature/recipe-v2", "fix/valve-seq"],
      description: "Clean-in-place skid controls and recipe management",
      controller: "Siemens S7-1500",
      controller_model: "CPU 1512SP-1 PN",
      status: "review",
      latest_release: "v0.9.4",
      latest_release_at: "2026-05-28T00:00:00.000Z",
      owner: "Taylor Chen",
      updated_at: ago(60 * 24),              // 1 day ago
      last_activity_by: "Taylor Chen",
      open_changes: 4,
      recent_commits: 3,
    },
    {
      id: 4,
      name: "Conveyor Zone 4",
      slug: "conveyor-zone-4",
      owner_id: 1,
      created_at: "2025-08-21T09:00:00.000Z",
      branches: ["main"],
      description: "Conveyor system, accumulation and diverters",
      controller: "Beckhoff TwinCAT",
      controller_model: "CX2043",
      status: "production",
      latest_release: "v3.2.1",
      latest_release_at: "2026-05-22T00:00:00.000Z",
      owner: "Marco Rossi",
      updated_at: ago(360),                  // 6 hours ago
      last_activity_by: "Jamie Davis",
      open_changes: 1,
      recent_commits: 1,
    },
    {
      id: 5,
      name: "Boiler Room Controls",
      slug: "boiler-room-controls",
      owner_id: 1,
      created_at: "2026-01-15T09:00:00.000Z",
      branches: ["main"],
      description: "Boiler sequencing, pumps, and burner management",
      controller: "Allen-Bradley",
      controller_model: "ControlLogix 5580",
      status: "draft",
      latest_release: "v1.5.0",
      latest_release_at: "2026-05-15T00:00:00.000Z",
      owner: "Dana Lee",
      updated_at: ago(60 * 24 * 2),          // 2 days ago
      last_activity_by: "Alex Morgan",
      open_changes: 0,
      recent_commits: 0,
    },
    {
      id: 6,
      name: "Case Packer West",
      slug: "case-packer-west",
      owner_id: 1,
      created_at: "2025-12-05T09:00:00.000Z",
      branches: ["main", "feature/discharge"],
      description: "Case packer, erector, and discharge controls",
      controller: "Siemens S7-1200",
      controller_model: "CPU 1215C DC/DC/Rly",
      status: "commissioning",
      latest_release: "v1.1.2",
      latest_release_at: "2026-05-08T00:00:00.000Z",
      owner: "Sam Okafor",
      updated_at: ago(60 * 24 * 5),          // 5 days ago
      last_activity_by: "Jamie Davis",
      open_changes: 1,
      recent_commits: 1,
    },
  ];
}
