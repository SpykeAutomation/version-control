// Pure helpers that turn a ChangeSet (the semantic diff for one commit) into the
// view data the commit detail page renders: a few summary counts, a flat list of
// change rows, and the names of files and symbols the commit touched. No React
// here — these are plain functions so they're easy to read and test.
import type {
  ChangeSet,
  EntityChange,
  ProgramChange,
  RoutineChange,
} from "../api/diff";

// The three change kinds shared across rows (comment_changed folds into
// "modified" so the table only shows added / modified / removed).
export type ChangeRowKind = "added" | "modified" | "removed";

// One row in the change-summary table.
export interface ChangeRow {
  kind: ChangeRowKind;
  // A short "Program / Routine"-style trail that locates the change.
  breadcrumb: string;
  // The thing that changed (a tag, routine, or program name).
  name: string;
  // A plain-language note about what changed.
  description: string;
}

// The headline counts shown as summary cards.
export interface ChangeSummary {
  rungsChanged: number;
  rungsAdded: number;
  rungsRemoved: number;
  rungsModified: number;
  routinesChanged: number;
  programsChanged: number;
  tagsChanged: number;
  // Everything else that changed: modules, data types, AOIs, tasks, and the
  // controller itself. Useful as a catch-all "other entities" count.
  entitiesChanged: number;
}

// Bundle of everything the page derives from one ChangeSet.
export interface ChangeView {
  summary: ChangeSummary;
  rows: ChangeRow[];
  files: string[];
  symbols: string[];
}

// True when a diff carries nothing — used for the empty state.
export function isEmptyChangeSet(cs: ChangeSet): boolean {
  return deriveChangeView(cs).rows.length === 0;
}

// A short, plain-language bullet describing one routine's change, leaning on its
// rung / line counts.
function routineBullet(r: RoutineChange): string {
  if (r.kind === "added") return `Added routine ${r.name}`;
  if (r.kind === "removed") return `Removed routine ${r.name}`;
  const rungs = r.rungs.length;
  if (rungs > 0) {
    return `Updated ${r.name} (${rungs} ${rungs === 1 ? "rung" : "rungs"} changed)`;
  }
  const lines = r.lines.length;
  if (lines > 0) {
    return `Edited ${r.name} (${lines} ${lines === 1 ? "line" : "lines"} changed)`;
  }
  if (r.formatting_only) return `Reformatted ${r.name}`;
  return `Updated ${r.name}`;
}

// Turn a semantic diff into the "Commit summary" bullet list shown on the commit
// page. Routines — the substantive logic edits — get a bullet each; tags and
// other entity kinds roll up into one line apiece. The list is capped so a large
// commit stays readable, with a trailing "+N more" when it overflows.
export function summarizeChangeSet(cs: ChangeSet, limit = 6): string[] {
  const bullets: string[] = [];

  for (const p of cs.programs) {
    if (p.kind === "added") {
      bullets.push(`Added program ${p.name}`);
      continue;
    }
    if (p.kind === "removed") {
      bullets.push(`Removed program ${p.name}`);
      continue;
    }
    for (const r of p.routines) bullets.push(routineBullet(r));
  }

  const tagCount =
    cs.controller_tags.length +
    cs.programs.reduce((n, p) => n + p.tags.length, 0);
  if (tagCount > 0) {
    bullets.push(`Updated ${tagCount} ${tagCount === 1 ? "tag" : "tags"}`);
  }

  const pushCount = (n: number, one: string, many: string) => {
    if (n > 0) bullets.push(`Updated ${n} ${n === 1 ? one : many}`);
  };
  pushCount(cs.modules.length, "module", "modules");
  pushCount(cs.data_types.length, "data type", "data types");
  pushCount(
    cs.add_on_instructions.length,
    "add-on instruction",
    "add-on instructions",
  );
  pushCount(cs.tasks.length, "task", "tasks");
  if (cs.controller.length > 0) {
    bullets.push(
      `Changed ${cs.controller.length} controller ${
        cs.controller.length === 1 ? "property" : "properties"
      }`,
    );
  }

  if (bullets.length > limit) {
    const shown = bullets.slice(0, limit);
    shown.push(`+${bullets.length - limit} more changes`);
    return shown;
  }
  return bullets;
}

// One non-routine section of the Changes tab: a titled group of entity changes
// (controller tags, modules, AOIs, …). Controller-level field edits wrap into a
// pseudo-entity so every group renders through the same table.
export interface EntityChangeGroup {
  title: string;
  entities: EntityChange[];
}

// The change-set's non-routine changes, grouped for display in the order the
// organizer presents them: controller first, then tags, programs' own fields
// and tags, and the remaining entity kinds.
export function entityChangeGroups(cs: ChangeSet): EntityChangeGroup[] {
  const groups: EntityChangeGroup[] = [];
  const push = (title: string, entities: EntityChange[]) => {
    if (entities.length > 0) groups.push({ title, entities });
  };

  push(
    "Controller properties",
    cs.controller.length > 0
      ? [{ name: "Controller", kind: "modified", fields: cs.controller }]
      : [],
  );
  push("Controller tags", cs.controller_tags);
  for (const p of cs.programs) {
    push(
      `Program ${p.name} — properties`,
      p.fields.length > 0
        ? [{ name: p.name, kind: p.kind, fields: p.fields }]
        : [],
    );
    push(`Program ${p.name} — tags`, p.tags);
  }
  push("Modules", cs.modules);
  push("Data types", cs.data_types);
  push("Add-on instructions", cs.add_on_instructions);
  push("Tasks", cs.tasks);
  return groups;
}

// Fold "comment_changed" (and any other kind) down to the three we display.
function rowKind(kind: string): ChangeRowKind {
  if (kind === "added") return "added";
  if (kind === "removed") return "removed";
  return "modified";
}

// A short, readable description of an entity change based on its kind and how
// many fields moved.
function entityDescription(e: EntityChange, noun: string): string {
  if (e.kind === "added") return `${noun} added`;
  if (e.kind === "removed") return `${noun} removed`;
  const n = e.fields.length;
  return n > 0
    ? `${n} ${n === 1 ? "field" : "fields"} changed`
    : `${noun} changed`;
}

// A description for a routine, leaning on its rung counts when present.
function routineDescription(r: RoutineChange): string {
  if (r.kind === "added") return "Routine added";
  if (r.kind === "removed") return "Routine removed";
  const added = r.rungs.filter((x) => x.kind === "added").length;
  const removed = r.rungs.filter((x) => x.kind === "removed").length;
  const modified = r.rungs.filter(
    (x) => x.kind === "modified" || x.kind === "comment_changed",
  ).length;
  const parts: string[] = [];
  if (added) parts.push(`${added} added`);
  if (modified) parts.push(`${modified} modified`);
  if (removed) parts.push(`${removed} removed`);
  if (parts.length > 0) return `Rungs ${parts.join(", ")}`;
  if (r.lines.length > 0) {
    return `${r.lines.length} ${r.lines.length === 1 ? "line" : "lines"} changed`;
  }
  if (r.formatting_only) return "Formatting only";
  return "Routine changed";
}

// Count every rung change inside a program's routines, split by kind.
function rungCounts(programs: ProgramChange[]): {
  added: number;
  removed: number;
  modified: number;
} {
  let added = 0;
  let removed = 0;
  let modified = 0;
  for (const p of programs) {
    for (const r of p.routines) {
      for (const rung of r.rungs) {
        if (rung.kind === "added") added += 1;
        else if (rung.kind === "removed") removed += 1;
        else modified += 1; // modified or comment_changed
      }
    }
  }
  return { added, removed, modified };
}

// Build the full view model from a ChangeSet in one pass.
export function deriveChangeView(cs: ChangeSet): ChangeView {
  const rows: ChangeRow[] = [];
  const files = new Set<string>();
  const symbols = new Set<string>();

  // Controller-level field edits collapse into a single row when present.
  if (cs.controller.length > 0) {
    rows.push({
      kind: "modified",
      breadcrumb: "Controller",
      name: "Controller",
      description: `${cs.controller.length} ${
        cs.controller.length === 1 ? "property" : "properties"
      } changed`,
    });
  }

  // Controller-level entity lists. Each entry is a row; tags also feed the
  // symbols list, modules/AOIs/data types/tasks feed the affected files list.
  const addEntities = (
    list: EntityChange[],
    noun: string,
    opts: { symbol?: boolean; file?: boolean } = {},
  ) => {
    for (const e of list) {
      rows.push({
        kind: rowKind(e.kind),
        breadcrumb: noun,
        name: e.name,
        description: entityDescription(e, noun),
      });
      if (opts.symbol) symbols.add(e.name);
      if (opts.file) files.add(e.name);
    }
  };

  addEntities(cs.controller_tags, "Controller tag", { symbol: true });
  addEntities(cs.modules, "Module", { file: true });
  addEntities(cs.data_types, "Data type", { file: true });
  addEntities(cs.add_on_instructions, "Add-on instruction", { file: true });
  addEntities(cs.tasks, "Task");

  // Programs and everything nested under them.
  let routinesChanged = 0;
  const programsChanged = cs.programs.length;
  for (const p of cs.programs) {
    files.add(p.name);
    rows.push({
      kind: rowKind(p.kind),
      breadcrumb: "Program",
      name: p.name,
      description:
        p.kind === "added"
          ? "Program added"
          : p.kind === "removed"
            ? "Program removed"
            : "Program changed",
    });

    for (const t of p.tags) {
      rows.push({
        kind: rowKind(t.kind),
        breadcrumb: `${p.name} / Tags`,
        name: t.name,
        description: entityDescription(t, "Tag"),
      });
      symbols.add(t.name);
    }

    for (const r of p.routines) {
      routinesChanged += 1;
      rows.push({
        kind: rowKind(r.kind),
        breadcrumb: p.name,
        name: r.name,
        description: routineDescription(r),
      });
      symbols.add(r.name);
    }
  }

  // Tags changed = controller tags plus every program tag.
  const tagsChanged =
    cs.controller_tags.length +
    cs.programs.reduce((sum, p) => sum + p.tags.length, 0);

  // Other entities: modules, data types, AOIs, tasks, and a changed controller.
  const entitiesChanged =
    cs.modules.length +
    cs.data_types.length +
    cs.add_on_instructions.length +
    cs.tasks.length +
    (cs.controller.length > 0 ? 1 : 0);

  const rc = rungCounts(cs.programs);
  const summary: ChangeSummary = {
    rungsChanged: rc.added + rc.removed + rc.modified,
    rungsAdded: rc.added,
    rungsRemoved: rc.removed,
    rungsModified: rc.modified,
    routinesChanged,
    programsChanged,
    tagsChanged,
    entitiesChanged,
  };

  return {
    summary,
    rows,
    files: [...files],
    symbols: [...symbols],
  };
}
