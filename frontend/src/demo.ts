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
