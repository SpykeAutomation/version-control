// Detail panels for the commit page's Files tab: what renders in the viewer
// stage when an organizer entity (not a program routine) is selected. Each
// panel lazy-loads its L5X section for the commit — cached per (sha, section),
// so re-opening a panel is instant — and presents it as tables, mirroring how
// Studio 5000 shows these categories.
import { useState, type ReactNode } from "react";
import type { TreeNode } from "../api/tree";
import type {
  AOILocalTag,
  AOIParameter,
  L5XAoiRoutine,
  L5XDataType,
  L5XModule,
  L5XTag,
} from "../api/l5x";
import {
  errorText,
  useL5xAoi,
  useL5xDataTypes,
  useL5xModules,
  useL5xTags,
} from "../api/queries";

interface PanelCtx {
  projectId?: number;
  sha: string;
  l5xPath: string | null;
}

// Routes a selected tree node to its panel by kind and key shape (the key
// prefixes are the backend tree contract: "aoi:", "datatype:aoi:", "motion:").
export function EntityPanel({
  node,
  ctx,
}: {
  node: TreeNode;
  ctx: PanelCtx;
}) {
  const key = node.key;
  if (node.kind === "aoi") return <AoiPanel name={node.label} node={node} ctx={ctx} />;
  if (node.kind === "routine" && key.startsWith("aoi:")) {
    return (
      <AoiRoutinePanel
        aoiName={key.slice("aoi:".length, key.indexOf("/routine:"))}
        routineName={node.label}
        ctx={ctx}
      />
    );
  }
  if (node.kind === "datatype" && key.startsWith("datatype:aoi:")) {
    // An Add-On-Defined data type is the AOI itself — its parameter list is
    // the type's structure.
    return <AoiPanel name={node.label} node={node} ctx={ctx} />;
  }
  if (node.kind === "datatype") return <DataTypePanel node={node} ctx={ctx} />;
  if (key === "folder:tags") return <TagGridPanel ctx={ctx} />;
  if (node.kind === "tag") return <TagDetailPanel node={node} ctx={ctx} />;
  if (key === "folder:io" || node.kind === "module") {
    return <ModuleTablePanel focus={node.kind === "module" ? node.label : undefined} ctx={ctx} />;
  }
  // Anything without a table view yet (tasks, program references, …).
  return (
    <div className="rcard-empty">
      <strong>{node.label}</strong>{" "}
      {node.status === "unchanged"
        ? "is unchanged in this commit."
        : "changed in this commit."}{" "}
      Detail for this item isn't shown in this view.
    </div>
  );
}

// ---- shared scaffolding ----

function Shell({
  title,
  sub,
  desc,
  children,
}: {
  title: string;
  sub?: string | null;
  desc?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="l5x-panel">
      <div className="l5x-panel-head">
        <span className="l5x-panel-title">{title}</span>
        {sub && <span className="l5x-panel-sub">{sub}</span>}
      </div>
      {desc && <p className="l5x-panel-desc">{desc}</p>}
      {children}
    </div>
  );
}

// Loading / error / removed-entity fallbacks shared by every panel. Returns
// null when the data is ready and the panel should render.
function loadState(
  q: { isPending: boolean; error: unknown },
  what: string,
): ReactNode | null {
  if (q.isPending) return <div className="rcard-empty">Loading {what}…</div>;
  if (q.error) {
    return (
      <div className="rcard-empty">
        {errorText(q.error, `Couldn't load ${what}.`)}
      </div>
    );
  }
  return null;
}

function removedNote(name: string, status: TreeNode["status"] | undefined, what: string) {
  return (
    <div className="rcard-empty">
      <strong>{name}</strong>{" "}
      {status === "removed"
        ? `was removed in this commit, so its ${what} isn't part of this version.`
        : `wasn't found in this commit's ${what}.`}
    </div>
  );
}

const dims = (d: number[] | null | undefined) =>
  d && d.length ? `[${d.join(",")}]` : "";
const flag = (b: boolean) => (b ? "Yes" : "");
// "NullType" is the export's way of saying "no radix" — noise, not a value.
const radix = (r: string | null | undefined) =>
  !r || r === "NullType" ? "" : r;

function Table({
  head,
  children,
}: {
  head: string[];
  children: ReactNode;
}) {
  return (
    <div className="dtable-scroll">
      <table className="dtable l5x-table">
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

// A column-driven table. Every column always renders, even when empty across
// the whole dataset — an unexpectedly empty column is itself information the
// reader may need to act on.
interface Col<T> {
  label: string;
  value: (row: T) => string;
  mono?: boolean;
  strong?: boolean;
}

function ColTable<T>({
  cols,
  rows,
  rowKey,
  focusKey,
}: {
  cols: Col<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  focusKey?: string;
}) {
  const shown = cols;
  return (
    <div className="dtable-scroll">
      <table className="dtable l5x-table">
        <thead>
          <tr>
            {shown.map((c) => (
              <th key={c.label}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={rowKey(r)}
              className={focusKey === rowKey(r) ? "l5x-row-focus" : undefined}
            >
              {shown.map((c) => (
                <td
                  key={c.label}
                  className={
                    c.strong ? "cell-strong" : c.mono ? "mono-cell" : "muted-cell"
                  }
                >
                  {c.value(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// A parameter value that is really a positional array flattened into one
// space-separated string (e.g. CIPAxisExceptionAction: ~60 entries, one per
// firmware-defined exception condition). Verbatim it's an unreadable wall of
// repeated words, so show a tally and expand on demand into a numbered list
// that scrolls inside its own cell — position matters (entry N maps to
// Rockwell's exception N), the table shouldn't grow by 60 rows.
const MULTI_VALUE_MIN = 8;

function MultiValueCell({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const tokens = text.trim().split(/\s+/);
  if (tokens.length < MULTI_VALUE_MIN) return <>{text}</>;

  const counts = new Map<string, number>();
  for (const t of tokens) counts.set(t, (counts.get(t) ?? 0) + 1);
  const groups = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const top = groups.slice(0, 5);
  return (
    <div className="l5x-multival">
      <div className="l5x-multival-sum">
        <span className="l5x-multival-count">{tokens.length} values</span>
        {top.map(([v, n]) => (
          <span className="l5x-multival-group" key={v}>
            {v} ×{n}
          </span>
        ))}
        {groups.length > top.length && (
          <span className="l5x-multival-count">
            +{groups.length - top.length} more
          </span>
        )}
        <button
          type="button"
          className="link-btn"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Hide list" : "Show all"}
        </button>
      </div>
      {open && (
        <ol className="l5x-multival-list">
          {tokens.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ---- Data type: member table ----

function DataTypePanel({ node, ctx }: { node: TreeNode; ctx: PanelCtx }) {
  const q = useL5xDataTypes(ctx.projectId, ctx.sha, ctx.l5xPath);
  const wait = loadState(q, "data types");
  if (wait) return wait;
  const dt: L5XDataType | undefined = q.data!.find((d) => d.name === node.label);
  if (!dt) return removedNote(node.label, node.status, "data types");

  // Studio 5000's editor hides the bit-backing host members; do the same.
  const members = dt.members.filter((m) => !m.hidden);
  const hidden = dt.members.length - members.length;
  return (
    <Shell
      title={dt.name}
      sub={dt.family === "StringFamily" ? "String" : "User-Defined Data Type"}
      desc={dt.description}
    >
      <ColTable
        rows={members}
        rowKey={(m) => m.name}
        cols={[
          { label: "Name", value: (m) => m.name, strong: true },
          { label: "Data Type", value: (m) => m.data_type, mono: true },
          { label: "Dimension", value: (m) => (m.dimension ? String(m.dimension) : "") },
          { label: "Radix", value: (m) => radix(m.radix) },
          { label: "External Access", value: (m) => m.external_access ?? "" },
          { label: "Description", value: (m) => m.description ?? "" },
        ]}
      />
      {hidden > 0 && (
        <p className="l5x-panel-note">
          {hidden} hidden host {hidden === 1 ? "member" : "members"} not shown.
        </p>
      )}
    </Shell>
  );
}

// ---- Controller tags: the full grid, or one tag's properties ----

function TagGridPanel({ ctx }: { ctx: PanelCtx }) {
  const q = useL5xTags(ctx.projectId, ctx.sha, ctx.l5xPath);
  const wait = loadState(q, "controller tags");
  if (wait) return wait;
  const tags = q.data!;
  return (
    <Shell title="Controller Tags" sub={`${tags.length} tags`}>
      <ColTable
        rows={tags}
        rowKey={(t) => t.name}
        cols={[
          { label: "Name", value: (t) => t.name, strong: true },
          { label: "Alias For", value: (t) => t.alias_for ?? "", mono: true },
          { label: "Data Type", value: (t) => t.data_type + dims(t.dimensions), mono: true },
          { label: "Value", value: (t) => t.value ?? "", mono: true },
          { label: "Radix", value: (t) => radix(t.radix) },
          { label: "Constant", value: (t) => flag(t.constant) },
          { label: "Class", value: (t) => t.tag_class ?? "" },
          { label: "Description", value: (t) => t.description ?? "" },
        ]}
      />
    </Shell>
  );
}

function TagDetailPanel({ node, ctx }: { node: TreeNode; ctx: PanelCtx }) {
  const q = useL5xTags(ctx.projectId, ctx.sha, ctx.l5xPath);
  const wait = loadState(q, "controller tags");
  if (wait) return wait;
  const tag: L5XTag | undefined = q.data!.find((t) => t.name === node.label);
  if (!tag) return removedNote(node.label, node.status, "controller tags");

  const rows: [string, string][] = [
    ["Data type", tag.data_type + dims(tag.dimensions)],
    ["Tag type", tag.tag_type ?? ""],
    ["Alias for", tag.alias_for ?? ""],
    ["Value", tag.value ?? ""],
    ["Radix", radix(tag.radix)],
    ["Constant", tag.constant ? "Yes" : "No"],
    ["External access", tag.external_access ?? ""],
    ["Class", tag.tag_class ?? ""],
  ];
  const motion = Object.entries(tag.motion_config ?? {});
  return (
    <Shell title={tag.name} sub={tag.data_type} desc={tag.description}>
      <Table head={["Property", "Value"]}>
        {rows
          .filter(([, v]) => v !== "")
          .map(([k, v]) => (
            <tr key={k}>
              <td className="cell-strong">{k}</td>
              <td className="mono-cell">{v}</td>
            </tr>
          ))}
      </Table>
      {motion.length > 0 && (
        <>
          <div className="l5x-panel-subhead">Motion configuration</div>
          <Table head={["Parameter", "Value"]}>
            {motion.map(([k, v]) => (
              <tr key={k}>
                <td className="cell-strong">{k}</td>
                <td className="mono-cell">
                  <MultiValueCell text={v} />
                </td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </Shell>
  );
}

// ---- I/O configuration: module table ----

function ModuleTablePanel({ focus, ctx }: { focus?: string; ctx: PanelCtx }) {
  const q = useL5xModules(ctx.projectId, ctx.sha, ctx.l5xPath);
  const wait = loadState(q, "I/O modules");
  if (wait) return wait;
  const modules = q.data!;
  if (focus && !modules.some((m) => m.name === focus)) {
    return removedNote(focus, undefined, "I/O configuration");
  }
  const address = (m: L5XModule) =>
    m.ports
      .map((p) => p.address)
      .filter(Boolean)
      .join(" / ");
  return (
    <Shell title="I/O Configuration" sub={`${modules.length} modules`}>
      <ColTable
        rows={modules}
        rowKey={(m) => m.name}
        focusKey={focus}
        cols={[
          { label: "Name", value: (m) => m.name, strong: true },
          { label: "Catalog Number", value: (m) => m.catalog_number ?? "", mono: true },
          { label: "Revision", value: (m) => (m.major != null ? `${m.major}.${m.minor ?? 0}` : "") },
          { label: "Parent", value: (m) => m.parent_module ?? "" },
          { label: "Address", value: address, mono: true },
          { label: "Inhibited", value: (m) => flag(m.inhibited) },
          { label: "Keying", value: (m) => m.ekey_state ?? "" },
        ]}
      />
    </Shell>
  );
}

// ---- AOI: parameters + local tags; routines render via AoiRoutinePanel ----

function AoiPanel({
  name,
  node,
  ctx,
}: {
  name: string;
  node: TreeNode;
  ctx: PanelCtx;
}) {
  const q = useL5xAoi(ctx.projectId, ctx.sha, ctx.l5xPath, name);
  if (q.error && node.status === "removed") {
    return removedNote(name, "removed", "Add-On Instructions");
  }
  const wait = loadState(q, name);
  if (wait) return wait;
  const aoi = q.data!;
  const sub = [
    aoi.revision ? `v${aoi.revision}` : null,
    aoi.vendor || null,
    aoi.edited_by ? `edited by ${aoi.edited_by}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Shell title={aoi.name} sub={sub || "Add-On Instruction"} desc={aoi.description}>
      <div className="l5x-panel-subhead">Parameters</div>
      <ColTable
        rows={aoi.parameters}
        rowKey={(p: AOIParameter) => p.name}
        cols={[
          { label: "Name", value: (p) => p.name, strong: true },
          { label: "Usage", value: (p) => p.usage ?? "" },
          { label: "Data Type", value: (p) => p.data_type + dims(p.dimensions), mono: true },
          { label: "Default", value: (p) => p.default_value ?? "", mono: true },
          { label: "Required", value: (p) => flag(p.required) },
          { label: "Visible", value: (p) => flag(p.visible) },
          { label: "Description", value: (p) => p.description ?? "" },
        ]}
      />
      {aoi.local_tags.length > 0 && (
        <>
          <div className="l5x-panel-subhead">Local tags</div>
          <ColTable
            rows={aoi.local_tags}
            rowKey={(t: AOILocalTag) => t.name}
            cols={[
              { label: "Name", value: (t) => t.name, strong: true },
              { label: "Data Type", value: (t) => t.data_type + dims(t.dimensions), mono: true },
              { label: "Default", value: (t) => t.default_value ?? "", mono: true },
              { label: "Description", value: (t) => t.description ?? "" },
            ]}
          />
        </>
      )}
    </Shell>
  );
}

function AoiRoutinePanel({
  aoiName,
  routineName,
  ctx,
}: {
  aoiName: string;
  routineName: string;
  ctx: PanelCtx;
}) {
  const q = useL5xAoi(ctx.projectId, ctx.sha, ctx.l5xPath, aoiName);
  const wait = loadState(q, `${aoiName} / ${routineName}`);
  if (wait) return wait;
  const rt: L5XAoiRoutine | undefined = q.data!.routines.find(
    (r) => r.name === routineName,
  );
  if (!rt) return removedNote(routineName, undefined, `routines of ${aoiName}`);

  const rungs = rt.content.rungs ?? [];
  const lines = rt.content.lines ?? [];
  return (
    <Shell title={`${aoiName} — ${rt.name}`} sub={rt.type} desc={rt.description}>
      {rungs.length > 0 ? (
        <Table head={["Rung", "Logic"]}>
          {rungs.map((r) => (
            <tr key={r.number}>
              <td className="muted-cell l5x-rung-num">{r.number}</td>
              <td>
                {r.comment && <div className="l5x-rung-comment">{r.comment}</div>}
                <code className="l5x-code">{r.text ?? ""}</code>
              </td>
            </tr>
          ))}
        </Table>
      ) : lines.length > 0 ? (
        <div className="l5x-st">
          {lines.map((l, i) => (
            <div className="cd-line" key={i}>
              <span className="cd-num">{l.number}</span>
              <span
                className="cd-code"
                style={{ paddingLeft: 8 + l.level * 14 }}
              >
                {l.text}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="rcard-empty">
          This routine's content isn't included in the export
          {rt.type !== "RLL" && rt.type !== "ST" ? ` (${rt.type} isn't renderable yet)` : ""}.
        </div>
      )}
    </Shell>
  );
}
