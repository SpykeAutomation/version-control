// Demo mode: run the whole flow with no backend. Enabled by VITE_DEMO=1.
// When on, the API helpers below return canned data instead of calling the
// server, so every screen (sign in, sign up, onboarding, done) is reachable
// locally for UI review.
import type { User } from "./api/auth";
import type { Project } from "./api/projects";
import type { MergeRequest } from "./api/mergeRequest";

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

// A fully-populated merge request for UI review in demo mode. Demo-only;
// never real or customer data. The rich review fields (reviewers, checks,
// impacted tags, ladder/structured-text diffs) aren't in the backend
// contract yet, so they only appear here — the real API returns what it has
// and the page shows empty states for the rest.
const _DEMO_MR_BASE = "2026-06-24T14:30:00Z";
const _hrsAgo = (h: number) =>
  new Date(Date.parse(_DEMO_MR_BASE) - h * 3600_000).toISOString();
const _minsAgo = (m: number) =>
  new Date(Date.parse(_DEMO_MR_BASE) - m * 60_000).toISOString();

export function demoMergeRequest(_slug: string, mrId: string): MergeRequest {
  return {
    id: mrId || "MR-027",
    title: "Add reject station logic",
    status: "review",
    sourceBranch: "feature/reject-station",
    targetBranch: "main",
    sourceCommits: 5,
    targetCommits: 128,
    author: "Jamie Wilson",
    authorAt: _hrsAgo(3),
    updatedAt: _hrsAgo(2),
    reviewers: [
      { name: "Alex Davis", role: "Controls Engineer", state: "approved" },
      { name: "Morgan Green", role: "Controls Engineer", state: "review" },
      { name: "Sam Clark", role: "Controls Engineer", state: "pending" },
    ],
    summary:
      "Adds reject station control logic with a photoeye interlock, increases the reject delay to 3000 ms, and adds a safety interlock before the motor runs.",
    bullets: [
      "Add reject photoeye interlock",
      "Increase reject delay from 2500 ms to 3000 ms",
      "Add E_Stop_OK contact before Motor_Run",
    ],
    rungsChanged: 28,
    routinesModified: 1,
    commentCount: 7,
    safetyReview: true,
    ladder: {
      routine: "Reject_Logic",
      networks: 3,
      left: {
        ref: "Current / main",
        version: "r1.0.2",
        rungs: [
          {
            number: 14,
            state: "modified",
            elements: [
              { kind: "no", tag: "Conveyor_Run", address: "I:0/2" },
              { kind: "no", tag: "Reject_Enable", address: "I:0/3" },
              { kind: "nc", tag: "Jam_Detect", address: "I:0/4" },
              { kind: "coil", tag: "Reject_Active", address: "O:2/0" },
            ],
          },
          {
            number: 27,
            state: "modified",
            elements: [
              { kind: "no", tag: "Reject_Active", address: "O:2/0" },
              { kind: "timer", tag: "Reject_Delay", address: "T4:1" },
              { kind: "coil", tag: "Reject_Fire", address: "O:2/1" },
            ],
          },
          {
            number: 45,
            state: "modified",
            elements: [
              { kind: "no", tag: "Safety_OK", address: "I:1/0" },
              { kind: "coil", tag: "Motor_Run", address: "O:1/0" },
            ],
          },
        ],
      },
      right: {
        ref: "Proposed / feature/reject-station",
        version: "latest",
        rungs: [
          {
            number: 14,
            state: "modified",
            elements: [
              { kind: "no", tag: "Conveyor_Run", address: "I:0/2" },
              { kind: "no", tag: "Reject_Enable", address: "I:0/3" },
              { kind: "no", tag: "Reject_Photoeye", address: "I:0/5", state: "added" },
              { kind: "nc", tag: "Jam_Detect", address: "I:0/4" },
              { kind: "coil", tag: "Reject_Active", address: "O:2/0" },
            ],
          },
          {
            number: 27,
            state: "modified",
            elements: [
              { kind: "no", tag: "Reject_Active", address: "O:2/0" },
              { kind: "timer", tag: "Reject_Delay", address: "T4:1", state: "added" },
              { kind: "coil", tag: "Reject_Fire", address: "O:2/1" },
            ],
          },
          {
            number: 45,
            state: "modified",
            elements: [
              { kind: "no", tag: "Safety_OK", address: "I:1/0" },
              { kind: "nc", tag: "E_Stop_OK", address: "I:1/1", state: "added" },
              { kind: "coil", tag: "Motor_Run", address: "O:1/0" },
            ],
          },
        ],
      },
    },
    code: {
      routine: "Reject_Control",
      left: {
        ref: "Current / main",
        version: "r1.0.2",
        lines: [
          { ln: 28, kind: "context", text: "IF Reject_Active AND NOT Reject_Delay.DN THEN" },
          { ln: 29, kind: "removed", text: "    Reject_Delay.IN := TRUE; PT := T#2500ms;" },
          { ln: 30, kind: "context", text: "ELSE" },
          { ln: 31, kind: "context", text: "    Reject_Delay.IN := FALSE;" },
          { ln: 32, kind: "context", text: "END_IF;" },
          { ln: 33, kind: "context", text: "" },
          { ln: 34, kind: "removed", text: "Motor_Run := Safety_OK AND Conveyor_Run_Cmd;" },
        ],
      },
      right: {
        ref: "Proposed / feature/reject-station",
        version: "latest",
        lines: [
          { ln: 28, kind: "context", text: "IF Reject_Active AND NOT Reject_Delay.DN THEN" },
          { ln: 29, kind: "added", text: "    Reject_Delay.IN := TRUE; PT := T#3000ms;" },
          { ln: 30, kind: "context", text: "ELSE" },
          { ln: 31, kind: "context", text: "    Reject_Delay.IN := FALSE;" },
          { ln: 32, kind: "context", text: "END_IF;" },
          { ln: 33, kind: "context", text: "" },
          { ln: 34, kind: "added", text: "Motor_Run := Safety_OK AND E_Stop_OK AND Conveyor_Run_Cmd;" },
        ],
      },
    },
    comments: [
      {
        author: "Morgan Green",
        role: "Controls Engineer",
        on: "Network 27",
        at: _hrsAgo(2),
        body: "Please confirm the reject delay increase is validated on Line 3. 3 seconds will impact throughput.",
      },
      {
        author: "Jamie Wilson",
        role: "Author",
        isAuthor: true,
        on: "Network 27",
        at: _hrsAgo(1),
        body: "Increase tested on Line 3 during FAT. No rejects missed with the 3 s delay at max speed.",
      },
      {
        author: "Alex Davis",
        role: "Safety Reviewer",
        on: "Network 45",
        at: _minsAgo(45),
        body: "Safety interlock change needs controls lead approval before merge.",
      },
    ],
    checks: [
      { label: "Lint", state: "passed" },
      { label: "Naming convention", state: "passed" },
      { label: "Safety review", state: "pending" },
    ],
    impactedTags: [
      "Reject_Active",
      "Reject_Photoeye",
      "Reject_Delay",
      "E_Stop_OK",
      "Motor_Run",
      "Safety_OK",
    ],
  };
}
