/* =========================================================================
 * Preview data for the repository view. Fabricated and demo-only — never
 * real or customer data. Lets the page render with content while the backend
 * endpoints that would supply it (commits, branches, file list, controller
 * status) don't exist yet; it's replaced by real API data once they do.
 * ========================================================================= */
import type { RepositoryDetail } from "../api/repository";

const now = Date.parse("2026-06-24T11:00:00Z");
const ago = (ms: number) => new Date(now - ms).toISOString();
const H = 3600_000;
const D = 24 * H;

export const TEMP_REPO_DETAIL: RepositoryDetail = {
  description:
    "Controls program for Packaging Line 3 including conveyors, case packer and reject system.",
  status: "production",
  controller: "Siemens S7-1500",
  controllerModel: "CPU 1516-3 PN/DP",
  latestRelease: "v2.14.0",
  lastCommitAt: ago(2 * H),
  lastCommitAuthor: "Alex Davis",
  openChangeRequests: 3,
  unresolvedComments: 5,
  commits: [
    { hash: "a7f3c8d", message: "Add jam detection timer", author: "Alex Davis", branch: "main", at: ago(2 * H), filesChanged: 2 },
    { hash: "7e2b110", message: "Tune startup sequence", author: "Alex Davis", branch: "main", at: ago(1 * D), filesChanged: 3 },
    { hash: "c2b91aa", message: "Interlock logic update", author: "Jamie Wilson", branch: "develop", at: ago(1 * D), filesChanged: 5 },
    { hash: "91ab23c", message: "Add reject sensor debounce", author: "Morgan Green", branch: "feature/reject-station", at: ago(36 * H), filesChanged: 1 },
    { hash: "d8e4b77", message: "Add reject confirmation signal", author: "Morgan Green", branch: "feature/reject-station", at: ago(2 * D), filesChanged: 3 },
    { hash: "5a1d88e", message: "Refactor permissive chain", author: "Jamie Wilson", branch: "develop", at: ago(2 * D), filesChanged: 4 },
    { hash: "3f9c021", message: "Update alarm thresholds", author: "Alex Davis", branch: "main", at: ago(3 * D), filesChanged: 2 },
    { hash: "f1a4d22", message: "Fix photoeye false trigger", author: "Sam Clark", branch: "hotfix/photoeye-fix", at: ago(4 * D), filesChanged: 1 },
    { hash: "b6c3d91", message: "Initial commissioning changes", author: "Alex Davis", branch: "commissioning/startup", at: ago(7 * D), filesChanged: 8 },
    { hash: "8e91d04", message: "Release v1.8.3", author: "Alex Davis", branch: "release/v1.8.3", at: ago(14 * D), filesChanged: 6 },
    { hash: "4bdf722", message: "Release v1.8.2", author: "Jamie Wilson", branch: "archive/v1.8.2", at: ago(30 * D), filesChanged: 7 },
  ],
  branches: [
    { name: "main", isDefault: true, isProtected: true, lastCommitHash: "a7f3c8d", lastCommitMessage: "Add jam detection timer", author: "Alex Davis", at: ago(2 * H), ahead: 0, behind: 0 },
    { name: "develop", isProtected: true, lastCommitHash: "c2b91aa", lastCommitMessage: "Interlock logic update", author: "Jamie Wilson", at: ago(1 * D), ahead: 1, behind: 2 },
    { name: "feature/reject-station", isProtected: false, lastCommitHash: "d8e4b77", lastCommitMessage: "Add reject confirmation signal", author: "Morgan Green", at: ago(2 * D), ahead: 0, behind: 5 },
    { name: "hotfix/photoeye-fix", isProtected: false, lastCommitHash: "f1a4d22", lastCommitMessage: "Fix photoeye false trigger", author: "Sam Clark", at: ago(4 * D), ahead: 3, behind: 0 },
    { name: "commissioning/startup", isProtected: true, lastCommitHash: "b6c3d91", lastCommitMessage: "Initial commissioning changes", author: "Alex Davis", at: ago(7 * D), ahead: 0, behind: 12 },
    { name: "release/v1.8.3", isProtected: true, lastCommitHash: "8e91d04", lastCommitMessage: "Release v1.8.3", author: "Alex Davis", at: ago(14 * D), ahead: 0, behind: 18 },
    { name: "archive/v1.8.2", isProtected: true, lastCommitHash: "4bdf722", lastCommitMessage: "Release v1.8.2", author: "Jamie Wilson", at: ago(30 * D), ahead: 0, behind: 32 },
  ],
  mergedBranches: [
    { name: "feature/conveyor-speed", into: "main", at: ago(3 * D) },
    { name: "hotfix/alarm-reset", into: "main", at: ago(7 * D) },
    { name: "bugfix/scale-overflow", into: "main", at: ago(14 * D) },
  ],
  changeRequests: [
    { id: "CR-027", title: "Add reject station logic", author: "Jamie Wilson", status: "open", at: ago(2 * D) },
    { id: "CR-026", title: "Update safety interlocks", author: "Morgan Green", status: "review", at: ago(3 * D) },
    { id: "CR-025", title: "Sensor calibration routine", author: "Sam Clark", status: "approved", at: ago(2 * D) },
    { id: "CR-024", title: "HMI alarm text updates", author: "Alex Davis", status: "merged", at: ago(7 * D) },
  ],
  details: [
    { label: "Description", value: "Controls program for Packaging Line 3 including conveyors, case packer and reject system." },
    { label: "Location", value: "Plant 1 › Line 3" },
    { label: "Owner", value: "Alex Davis" },
    { label: "Created", value: "May 14, 2025" },
  ],
  tags: [
    { label: "packaging" },
    { label: "line-3" },
    { label: "production", tone: "green" },
    { label: "critical", tone: "red" },
    { label: "siemens" },
  ],
  linkedController: {
    id: "PLC-PL3-01",
    online: true,
    ip: "10.10.3.15",
    lastSeen: ago(2 * 60_000),
    inSync: true,
  },
  files: { totalFiles: 1248, totalSize: "48.3 MB" },
  fileList: [
    {
      name: "MainProgram.L5X",
      kind: "program",
      description: "Main program cycle",
      size: "412 KB",
      modifiedAt: ago(2 * H),
      modifiedBy: "Alex Davis",
      content: {
        type: "ladder",
        routines: [
          {
            name: "MainRoutine",
            rungs: [
              {
                number: 0,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Start_PB", address: "I:1/0" },
                  { kind: "nc", tag: "Stop_PB", address: "I:1/1" },
                  { kind: "coil", tag: "System_Run", address: "O:2/0" },
                ],
              },
              {
                number: 1,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "System_Run", address: "O:2/0" },
                  { kind: "nc", tag: "Fault_Active", address: "B3:0/2" },
                  { kind: "timer", tag: "Startup_Delay", address: "T4:0" },
                ],
              },
              {
                number: 2,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Startup_Delay.DN", address: "T4:0/DN" },
                  { kind: "coil-set", tag: "Ready", address: "B3:0/0" },
                ],
              },
            ],
          },
          {
            name: "Startup",
            rungs: [
              {
                number: 0,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "System_Run", address: "O:2/0" },
                  { kind: "nc", tag: "Fault_Active", address: "B3:0/2" },
                  { kind: "coil", tag: "Drives_Enabled", address: "O:2/1" },
                ],
              },
              {
                number: 1,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Drives_Enabled", address: "O:2/1" },
                  { kind: "timer", tag: "Warmup_Timer", address: "T4:1" },
                ],
              },
            ],
          },
        ],
      },
    },
    {
      name: "Reject_Logic.L5X",
      kind: "routine",
      description: "Reject station sequence",
      size: "86 KB",
      modifiedAt: ago(2 * H),
      modifiedBy: "Alex Davis",
      content: {
        type: "ladder",
        routines: [
          {
            name: "Reject_Logic",
            rungs: [
              {
                number: 0,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Reject_Sensor", address: "I:3/4" },
                  { kind: "no", tag: "Ready", address: "B3:0/0" },
                  { kind: "timer", tag: "Reject_Pulse", address: "T4:2" },
                ],
              },
              {
                number: 1,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Reject_Pulse.TT", address: "T4:2/TT" },
                  { kind: "coil", tag: "Reject_Valve", address: "O:4/2" },
                ],
              },
            ],
          },
        ],
      },
    },
    {
      name: "Conveyor_Control.L5X",
      kind: "routine",
      description: "Conveyor run and jam logic",
      size: "124 KB",
      modifiedAt: ago(1 * D),
      modifiedBy: "Jamie Wilson",
      content: {
        type: "ladder",
        routines: [
          {
            name: "Conveyor_Control",
            rungs: [
              {
                number: 0,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Ready", address: "B3:0/0" },
                  { kind: "nc", tag: "Jam_Detected", address: "B3:1/0" },
                  { kind: "coil", tag: "Conveyor_Fwd", address: "O:5/0" },
                ],
              },
              {
                number: 1,
                state: "unchanged",
                elements: [
                  { kind: "nc", tag: "Photoeye", address: "I:3/0" },
                  { kind: "timer", tag: "Jam_Timer", address: "T4:5" },
                ],
              },
              {
                number: 2,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Jam_Timer.DN", address: "T4:5/DN" },
                  { kind: "coil-set", tag: "Jam_Detected", address: "B3:1/0" },
                ],
              },
            ],
          },
        ],
      },
    },
    {
      name: "Interlocks.L5X",
      kind: "routine",
      description: "Safety interlock chain",
      size: "72 KB",
      modifiedAt: ago(2 * D),
      modifiedBy: "Morgan Green",
      content: {
        type: "ladder",
        routines: [
          {
            name: "Interlocks",
            rungs: [
              {
                number: 0,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "EStop_OK", address: "I:0/0" },
                  { kind: "no", tag: "Guard_Closed", address: "I:0/1" },
                  { kind: "coil", tag: "Safety_OK", address: "B3:2/0" },
                ],
              },
              {
                number: 1,
                state: "unchanged",
                elements: [
                  { kind: "nc", tag: "Safety_OK", address: "B3:2/0" },
                  { kind: "coil-set", tag: "Fault_Active", address: "B3:0/2" },
                ],
              },
              {
                number: 2,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Reset_PB", address: "I:0/2" },
                  { kind: "no", tag: "Safety_OK", address: "B3:2/0" },
                  { kind: "coil", tag: "Fault_Reset", address: "B3:2/1" },
                ],
              },
            ],
          },
        ],
      },
    },
    {
      name: "Alarms.L5X",
      kind: "routine",
      description: "Alarm and fault handling",
      size: "64 KB",
      modifiedAt: ago(3 * D),
      modifiedBy: "Sam Clark",
      content: {
        type: "ladder",
        routines: [
          {
            name: "Alarms",
            rungs: [
              {
                number: 0,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Fault_Active", address: "B3:0/2" },
                  { kind: "timer", tag: "Alarm_Delay", address: "T4:8" },
                ],
              },
              {
                number: 1,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Alarm_Delay.DN", address: "T4:8/DN" },
                  { kind: "coil", tag: "Alarm_Horn", address: "O:6/0" },
                ],
              },
              {
                number: 2,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Ack_PB", address: "I:0/3" },
                  { kind: "coil", tag: "Alarm_Ack", address: "B3:3/0" },
                ],
              },
            ],
          },
        ],
      },
    },
    {
      name: "Diagnostics.L5X",
      kind: "routine",
      description: "I/O and device diagnostics",
      size: "48 KB",
      modifiedAt: ago(5 * D),
      modifiedBy: "Jamie Wilson",
      content: {
        type: "ladder",
        routines: [
          {
            name: "Diagnostics",
            rungs: [
              {
                number: 0,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "Photoeye", address: "I:3/0" },
                  { kind: "counter", tag: "Part_Count", address: "C5:0" },
                ],
              },
              {
                number: 1,
                state: "unchanged",
                elements: [
                  { kind: "nc", tag: "Comm_OK", address: "B3:4/0" },
                  { kind: "coil-set", tag: "Comm_Fault", address: "B3:4/1" },
                ],
              },
              {
                number: 2,
                state: "unchanged",
                elements: [
                  { kind: "no", tag: "System_Run", address: "O:2/0" },
                  { kind: "coil", tag: "Heartbeat", address: "O:6/7" },
                ],
              },
            ],
          },
        ],
      },
    },
  ],
};
