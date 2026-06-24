// Demo mode: run the whole flow with no backend. Enabled by VITE_DEMO=1.
// When on, the API helpers below return canned data instead of calling the
// server, so every screen (sign in, sign up, onboarding, done) is reachable
// locally for UI review.
import type { User } from "./api/auth";
import type { Project } from "./api/projects";

export const DEMO = import.meta.env.VITE_DEMO === "1";

export const demoUser: User = {
  id: 1,
  name: "Demo Engineer",
  email: "demo@spyke.local",
  username: "demo",
};

export const demoProject: Project = {
  id: 1,
  name: "demo-project",
  slug: "demo-project",
  owner_id: 1,
  created_at: "2026-01-01T00:00:00Z",
  branches: ["main"],
};

// A small set of neutral placeholder projects so the Projects table renders
// with content in demo mode. Demo-only; never real or customer data.
export const demoProjects: Project[] = [
  { id: 1, name: "atlas", slug: "atlas", owner_id: 1, created_at: "2026-06-23T08:10:00Z", branches: ["main", "develop"] },
  { id: 2, name: "beacon", slug: "beacon", owner_id: 1, created_at: "2026-06-21T14:00:00Z", branches: ["main"] },
  { id: 3, name: "cypress", slug: "cypress", owner_id: 1, created_at: "2026-06-18T16:45:00Z", branches: ["main", "develop", "release/1.0"] },
  { id: 4, name: "delta", slug: "delta", owner_id: 1, created_at: "2026-06-09T11:20:00Z", branches: ["main", "develop"] },
  { id: 5, name: "ember", slug: "ember", owner_id: 1, created_at: "2026-05-28T09:30:00Z", branches: ["main"] },
];
