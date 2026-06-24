/* =========================================================================
 * Preview data for the Compare page. Fabricated and demo-only — never real or
 * customer data. Lets the page render with a logic diff while the backend
 * comparison endpoint isn't wired up here yet; replaced by real API data once
 * it is.
 * ========================================================================= */
import type { Comparison } from "../api/compare";

const now = Date.parse("2026-06-24T09:30:00Z");
const hrs = (h: number) => new Date(now - h * 3600_000).toISOString();

export const TEMP_COMPARISON: Comparison = {
  repository: "Packaging Line 3",
  controller: "Siemens S7-1500",
  left: { ref: "main", version: "v2.13.2" },
  right: { ref: "feature/reject-station", version: "latest" },
  summary: {
    rungsChanged: 28,
    rungsModified: 16,
    rungsAdded: 8,
    rungsRemoved: 4,
    networksAdded: 9,
    instructionsAdded: 412,
    commentsUpdated: 7,
    safetyImpacting: 3,
  },
  diff: {
    routine: "Reject_Logic",
    left: {
      ref: "Current / main",
      version: "v2.13.2",
      rungs: [
        {
          number: 14,
          state: "modified",
          elements: [
            { kind: "no", tag: "Conveyor_Start", address: "%I0.0" },
            { kind: "no", tag: "Reject_Enable", address: "%I0.1" },
            { kind: "nc", tag: "Jam_Sensor", address: "%I0.2" },
            { kind: "coil", tag: "Reject_Active", address: "%Q2.0" },
          ],
        },
        {
          number: 27,
          state: "modified",
          elements: [
            { kind: "no", tag: "Reject_Active", address: "%Q2.0" },
            { kind: "timer", tag: "Reject_Delay", address: "%T1" },
            { kind: "coil", tag: "Reject_Fire", address: "%Q2.1" },
          ],
        },
        {
          number: 9,
          state: "removed",
          elements: [
            { kind: "no", tag: "Test_Mode", address: "%I3.0", state: "removed" },
            { kind: "coil", tag: "Test_Lamp", address: "%Q3.0", state: "removed" },
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
            { kind: "no", tag: "Conveyor_Start", address: "%I0.0" },
            { kind: "no", tag: "Reject_Enable", address: "%I0.1" },
            { kind: "no", tag: "Reject_Photoeye", address: "%I0.5", state: "added" },
            { kind: "nc", tag: "Jam_Sensor", address: "%I0.2" },
            { kind: "coil", tag: "Reject_Active", address: "%Q2.0" },
          ],
        },
        {
          number: 27,
          state: "modified",
          elements: [
            { kind: "no", tag: "Reject_Active", address: "%Q2.0" },
            { kind: "timer", tag: "Reject_Delay", address: "%T1", state: "added" },
            { kind: "coil", tag: "Reject_Fire", address: "%Q2.1" },
          ],
        },
        {
          number: 41,
          state: "added",
          elements: [
            { kind: "no", tag: "Run_Request", address: "%I1.0", state: "added" },
            { kind: "nc", tag: "EStop_OK", address: "%I1.1", state: "added" },
            { kind: "coil", tag: "Motor_Run", address: "%Q1.0", state: "added" },
          ],
        },
      ],
    },
  },
  changes: [
    {
      kind: "added",
      network: 14,
      change: "Added rung",
      description: "Added reject photoeye interlock in reject-active logic.",
      impact: "low",
      author: "Jamie Wilson",
      at: hrs(3),
    },
    {
      kind: "modified",
      network: 27,
      change: "Modified timer",
      description: "Changed Reject_Delay preset from 2000 ms to 3000 ms.",
      impact: "medium",
      author: "Sam Clark",
      at: hrs(3),
    },
    {
      kind: "added",
      network: 41,
      change: "Added safety interlock",
      description: "Added E_Stop_OK contact before Motor_Run coil.",
      impact: "high",
      author: "Morgan Green",
      at: hrs(3),
    },
    {
      kind: "removed",
      network: 9,
      change: "Removed network",
      description: "Removed Test_Mode test lamp network.",
      impact: "low",
      author: "Alex Davis",
      at: hrs(4),
    },
  ],
  comments: [
    {
      author: "Jamie Wilson",
      at: hrs(3),
      body: "Added photoeye interlock to prevent ejects when no part is present.",
    },
    {
      author: "Sam Clark",
      at: hrs(2),
      body: "Increased delay to account for longer actuator stroke time.",
    },
    {
      author: "Morgan Green",
      at: hrs(1),
      body: "E-Stop contact added before motor coil for PLC compliance.",
    },
  ],
  symbols: [
    "Reject_Photoeye",
    "Reject_Delay",
    "Motor_Run",
    "Safety_OK",
    "Reject_Active",
    "EStop_OK",
  ],
  files: [
    { name: "MainProgram.OB1", detail: "Networks 14, 27, 45, 52" },
    { name: "RejectTimers", detail: "Preset / accumulator change" },
  ],
};
