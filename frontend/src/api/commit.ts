// Types and data access for the commit review view. The page reads a
// CommitDetail from getCommit(): in demo mode it's canned data; against the real
// API it's mapped from the commit meta + ladder-diff endpoints. Ladder rungs
// reuse the IR model from ./diff so the panels share the LadderDiff renderer,
// and the file/routine grouping reuses the shapes from ./mergeRequest so the two
// review pages stay structurally aligned.
import { ApiError } from "./client";
import { listProjects } from "./projects";
import { listCommits } from "./commits";
import { getCommitDiff, getCommitLadderDiff } from "./diff";
import type {
  ChangeSet,
  IRElement,
  IRRoutineLadderDiff,
  IRRungDiff,
} from "./diff";
import type { MRCodeDiff, MRComment, PRFile, PRRoutineChange } from "./mergeRequest";
import { deriveChangeView, summarizeChangeSet } from "../lib/changeset";

// One changed file's line tally, shown in the rail's "Files changed" card.
export interface CommitFileStat {
  name: string;
  additions: number;
  deletions: number;
}

export interface CommitDetail {
  sha: string; // short sha, e.g. "a7f3c9d"
  title: string; // commit headline
  branch: string; // branch the commit is on
  author: string;
  authorRole: string;
  authoredAt: string; // ISO
  parentSha: string; // short sha of the parent commit
  filesChanged: number;
  additions: number;
  deletions: number;
  message: string; // commit message headline (repeated in the message card)
  summary: string[]; // bullet points describing the change
  rungsChanged: number;
  routinesModified: number;
  commentCount: number;
  // Changes grouped by file; each file carries ladder / structured-text routine
  // diffs (same shape the merge-request page uses).
  files: PRFile[];
  comments: MRComment[];
  impactedTags: string[];
  fileStats: CommitFileStat[]; // per-file +/- tallies for the rail
}

// --- Backend wiring ---
interface CommitOut {
  sha: string;
  message: string;
  author: string;
  at: string;
}

function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

const EMPTY_CHANGESET: ChangeSet = {
  controller: [],
  modules: [],
  data_types: [],
  add_on_instructions: [],
  controller_tags: [],
  programs: [],
  tasks: [],
};

// Map a real commit (meta + ladder diff + semantic change-set) onto the page's
// view model. The summary bullets, impacted tags and headline counts are derived
// from the change-set (the semantic diff), so they reflect the actual commit.
// The remaining review fields (comments, per-file line tallies) aren't in the
// backend contract yet, so they come back empty — same convention as the
// merge-request map.
function mapCommit(
  sha: string,
  branch: string,
  commits: CommitOut[],
  ladder: IRRoutineLadderDiff[],
  changeSet: ChangeSet,
): CommitDetail {
  const idx = commits.findIndex((c) => c.sha === sha || shortSha(c.sha) === sha);
  const meta = idx >= 0 ? commits[idx] : null;
  const parent = idx >= 0 ? commits[idx + 1] : undefined;

  // Group the ladder routines under their controller (the L5X file). A commit is
  // one controller file, so all routines fall under one file entry.
  const files: PRFile[] =
    ladder.length === 0
      ? []
      : [
          {
            name: ladder[0].controller ?? "Controller",
            changes: ladder.map<PRRoutineChange>((r) => ({
              routine: r.routine ?? "Routine",
              kind: "ladder",
              ladder: r,
            })),
          },
        ];

  const view = deriveChangeView(changeSet);
  const message = meta?.message ?? `Commit ${shortSha(sha)}`;
  return {
    sha: shortSha(sha),
    title: message,
    branch,
    author: meta?.author ?? "Unknown",
    authorRole: "",
    authoredAt: meta?.at ?? new Date(0).toISOString(),
    parentSha: parent ? shortSha(parent.sha) : "—",
    filesChanged: view.files.length || files.length,
    additions: 0,
    deletions: 0,
    message,
    summary: summarizeChangeSet(changeSet),
    rungsChanged: view.summary.rungsChanged,
    routinesModified: view.summary.routinesChanged,
    commentCount: 0,
    files,
    comments: [],
    impactedTags: view.symbols,
    fileStats: [],
  };
}

// Load a commit for the review page: resolve the project by slug, then fetch the
// commit list (for meta) and the ladder diff. When the backend can't be reached
// the page falls back to a self-contained demo commit so the view is still
// explorable without a running server.
export async function getCommit(slug: string, sha: string): Promise<CommitDetail> {
  try {
    const projects = await listProjects();
    const project = projects.find((p) => p.slug === slug);
    if (!project) throw new Error("Project not found");
    const branch = project.branches[0] ?? "main";
    const [commits, ladder, changeSet] = await Promise.all([
      listCommits(project.id, branch).catch(() => [] as CommitOut[]),
      getCommitLadderDiff(project.id, sha)
        .then((d) => d.routines)
        .catch(() => [] as IRRoutineLadderDiff[]),
      getCommitDiff(project.id, sha).catch(() => EMPTY_CHANGESET),
    ]);
    return mapCommit(sha, branch, commits as CommitOut[], ladder, changeSet);
  } catch (err) {
    // A status-0 ApiError means the server is unreachable (e.g. no backend in
    // local dev) — show the demo commit rather than an error banner.
    if (err instanceof ApiError && err.status === 0) return demoCommit(sha);
    throw err;
  }
}

// --- Demo data ---
// A fully populated, synthetic commit used when no backend is reachable.
// Everything here is invented sample content, not derived from any real file.

// --- IR ladder builders (feed the shared LadderDiff renderer) ---
type ElStatus = IRElement["status"];

function contact(
  label: string,
  form: "no" | "nc",
  status: ElStatus = "unchanged",
): IRElement {
  return { kind: "contact", status, io: "input", form, label };
}

function coil(label: string, status: ElStatus = "unchanged"): IRElement {
  return { kind: "coil", status, io: "output", form: "ote", label };
}

// A timer box. The before/after sides carry a status so the box paints
// red-on-the-left, green-on-the-right like a modified element in the mockup.
function tonBox(timer: string, preset: string, status: ElStatus): IRElement {
  return {
    kind: "box",
    status,
    io: "output",
    mnemonic: "TON",
    operands: [
      { label: "Timer", value: timer, changed: false },
      { label: "Preset", value: preset, changed: false },
    ],
  };
}

function modRung(number: number, before: IRElement[], after: IRElement[]): IRRungDiff {
  return {
    status: "modified",
    old_number: number,
    new_number: number,
    before,
    after,
  };
}

function ladderRoutine(routine: string, rungs: IRRungDiff[]): IRRoutineLadderDiff {
  return {
    routine,
    controller: "Main.ap16",
    routine_type: "rll",
    old_label: "Previous (c2b91aa)",
    new_label: "Current (a7f3c9d)",
    summary: {
      rungs_modified: rungs.length,
      rungs_added: 0,
      rungs_removed: 0,
      additions: 0,
      removals: 0,
    },
    rungs,
  };
}

export function demoCommit(sha: string): CommitDetail {
  const now = Date.now();
  const ago = (minutes: number) => new Date(now - minutes * 60_000).toISOString();
  const short = sha && /[0-9a-f]/i.test(sha) ? shortSha(sha) : "a7f3c9d";

  // The ladder routine: three modified networks, each painting the changed
  // element red on the "before" side and green on the "after" side.
  const conveyorStart = ladderRoutine("ConveyorStart", [
    // Network 10: jam-delay timer preset raised from 3.0s to 5.0s.
    modRung(
      9,
      [
        contact("Start_PB", "no"),
        contact("Jam_Sensor", "no"),
        tonBox("Jam_Delay", "3.0s", "removed"),
        coil("Conveyor_Run_Cmd"),
      ],
      [
        contact("Start_PB", "no"),
        contact("Jam_Sensor", "no"),
        tonBox("Jam_Delay", "5.0s", "added"),
        coil("Conveyor_Run_Cmd"),
      ],
    ),
    // Network 20: Conveyor_Run_Cmd interlock flipped from normally-closed to
    // normally-open.
    modRung(
      19,
      [
        contact("Reject_Active", "no"),
        contact("Conveyor_Run_Cmd", "nc", "removed"),
        coil("Reject_Solenoid"),
      ],
      [
        contact("Reject_Active", "no"),
        contact("Conveyor_Run_Cmd", "no", "added"),
        coil("Reject_Solenoid"),
      ],
    ),
    // Network 30: Jam_Delay.DN done-bit contact flipped from NC to NO.
    modRung(
      29,
      [
        contact("Reset_PB", "no"),
        contact("Jam_Delay.DN", "nc", "removed"),
        coil("Jam_Active"),
      ],
      [
        contact("Reset_PB", "no"),
        contact("Jam_Delay.DN", "no", "added"),
        coil("Jam_Active"),
      ],
    ),
  ]);

  // The structured-text routine: the jam timer preset edited in code.
  const jamLogic: MRCodeDiff = {
    routine: "JamDetect",
    changes: 1,
    left: {
      ref: "Previous (c2b91aa)",
      version: "c2b91aa",
      lines: [
        { ln: 18, kind: "context", text: "IF Jam_Sensor AND NOT Jam_Timer.DN THEN" },
        { ln: 19, kind: "removed", text: "    Jam_Timer(IN := TRUE, PT := ⟦T#3s⟧);" },
        { ln: 20, kind: "context", text: "ELSE" },
        { ln: 21, kind: "context", text: "    Jam_Timer(IN := FALSE);" },
        { ln: 22, kind: "context", text: "END_IF;" },
        { ln: 23, kind: "context", text: "Jam_Active := Jam_Timer.DN;" },
      ],
    },
    right: {
      ref: "Current (a7f3c9d)",
      version: short,
      lines: [
        { ln: 18, kind: "context", text: "IF Jam_Sensor AND NOT Jam_Timer.DN THEN" },
        { ln: 19, kind: "added", text: "    Jam_Timer(IN := TRUE, PT := ⟦T#5s⟧);" },
        { ln: 20, kind: "context", text: "ELSE" },
        { ln: 21, kind: "context", text: "    Jam_Timer(IN := FALSE);" },
        { ln: 22, kind: "context", text: "END_IF;" },
        { ln: 23, kind: "context", text: "Jam_Active := Jam_Timer.DN;" },
      ],
    },
  };

  // The semantic diff for this commit. The summary bullets below are derived
  // from it, the same way the real commit page derives them from the backend
  // change-set, so the preview demonstrates the live behaviour.
  const impactedTags = [
    "Jam_Timer",
    "Conveyor_Run_Cmd",
    "Alarm_Jam",
    "Jam_Sensor",
    "Reject_Active",
  ];
  const demoChangeSet: ChangeSet = {
    ...EMPTY_CHANGESET,
    programs: [
      {
        name: "MainProgram",
        kind: "modified",
        fields: [],
        tags: impactedTags.map((name) => ({ name, kind: "modified", fields: [] })),
        routines: [
          {
            name: "ConveyorStart",
            kind: "modified",
            routine_type: "rll",
            fields: [],
            rungs: [
              { kind: "modified" },
              { kind: "modified" },
              { kind: "modified" },
            ],
            lines: [],
            formatting_only: false,
          },
          {
            name: "JamDetect",
            kind: "modified",
            routine_type: "st",
            fields: [],
            rungs: [],
            lines: [{ kind: "modified" }],
            formatting_only: false,
          },
        ],
      },
    ],
  };

  return {
    sha: short,
    title: "Add jam detection timer",
    branch: "main",
    author: "Alex Davis",
    authorRole: "Controls Engineer",
    authoredAt: ago(120),
    parentSha: "c2b91aa",
    filesChanged: 4,
    additions: 112,
    deletions: 38,
    message: "Add jam detection timer",
    summary: summarizeChangeSet(demoChangeSet),
    rungsChanged: 12,
    routinesModified: 1,
    commentCount: 5,
    files: [
      {
        name: "Main.ap16",
        changes: [
          { routine: "ConveyorStart", kind: "ladder", ladder: conveyorStart },
          { routine: "JamDetect", kind: "structured", code: jamLogic },
        ],
      },
    ],
    comments: [
      {
        author: "Morgan Green",
        role: "Controls Engineer",
        on: "line 19",
        at: ago(120),
        body: "Increased timer to 5s to reduce false jam alarms on the conveyor.",
      },
      {
        author: "Jamie Wilson",
        role: "Controls Engineer",
        on: "line 19",
        at: ago(60),
        body: "Looks good. Matches what we discussed in the standup.",
      },
      {
        author: "Alex Davis",
        role: "Controls Engineer",
        isAuthor: true,
        on: "line 19",
        at: ago(45),
        body: "Thanks all—tested on line and working as expected.",
      },
    ],
    impactedTags,
    fileStats: [
      { name: "Main.ap16", additions: 64, deletions: 18 },
      { name: "RejectControl.st", additions: 22, deletions: 10 },
      { name: "HMI_Alarms.csv", additions: 12, deletions: 4 },
      { name: "Commissioning_Notes.md", additions: 14, deletions: 6 },
    ],
  };
}
