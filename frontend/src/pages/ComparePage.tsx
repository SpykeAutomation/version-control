import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeftRight,
  Box,
  ChevronDown,
  CircleAlert,
  CirclePlus,
  Cpu,
  Download,
  FileCode2,
  GitBranch,
  Maximize2,
  MessageSquare,
  Minus,
  Pencil,
  Plus,
  Settings2,
  SplitSquareHorizontal,
} from "lucide-react";
import { useTopBarActions } from "../app/TopBarActions";
import { RungView } from "../components/Ladder";
import type {
  ChangeKind,
  ChangeRow,
  Comparison,
  Impact,
  ReviewComment,
  RoutineSide,
} from "../api/compare";
import { timeAgo } from "../lib/time";

const ZOOMS = [0.8, 0.9, 1, 1.1, 1.25, 1.5];

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function ComparePage() {
  // The backend comparison endpoint isn't wired up here yet; until it is, the
  // page shows the empty state.
  const [comparison] = useState<Comparison | null>(null);

  const [view, setView] = useState<"ladder" | "text">("ladder");
  const [zoomIdx, setZoomIdx] = useState(2);

  const actions = (
    <>
      <button className="btn btn-outline btn-sm">
        <Settings2 size={15} strokeWidth={1.8} />
        Options
      </button>
      <button className="btn btn-primary btn-sm">
        <SplitSquareHorizontal size={15} strokeWidth={2} />
        Review &amp; compare
      </button>
    </>
  );

  useTopBarActions(actions);

  return (
      <div className="app-scroll">
        <div className="mr-page">
          <nav className="crumb">
            <Link to="/organization">Repositories</Link>
            <span className="crumb-sep">/</span>
            <span>Compare</span>
          </nav>

          <header className="mr-head">
            <div className="mr-head-main">
              <div className="mr-title-row">
                <h1 className="mr-title">Compare changes</h1>
              </div>
              <p className="mr-sub">
                Review ladder logic changes between branches, releases, and commits.
              </p>
            </div>
          </header>

          <div className="page-grid compare-grid">
          <div className="page-main">
            <CompareBar c={comparison} />

            {!comparison ? (
              <EmptyCompare />
            ) : (
              <>
                <SummaryCards c={comparison} />

                <div className="diff-toolbar">
                  <div className="seg">
                    <button
                      className={`seg-btn${view === "ladder" ? " active" : ""}`}
                      onClick={() => setView("ladder")}
                    >
                      Ladder
                    </button>
                    <button
                      className={`seg-btn${view === "text" ? " active" : ""}`}
                      onClick={() => setView("text")}
                    >
                      Text
                    </button>
                  </div>
                  <div className="zoom">
                    <button
                      className="zoom-btn"
                      aria-label="Zoom out"
                      onClick={() => setZoomIdx((i) => Math.max(0, i - 1))}
                    >
                      <Minus size={14} strokeWidth={2} />
                    </button>
                    <span className="zoom-val">{Math.round(ZOOMS[zoomIdx] * 100)}%</span>
                    <button
                      className="zoom-btn"
                      aria-label="Zoom in"
                      onClick={() => setZoomIdx((i) => Math.min(ZOOMS.length - 1, i + 1))}
                    >
                      <Plus size={14} strokeWidth={2} />
                    </button>
                    <button className="zoom-btn" aria-label="Fit to width">
                      <Maximize2 size={13} strokeWidth={1.8} />
                    </button>
                  </div>
                </div>

                <div className="diff-panels">
                  <DiffPanel
                    side="left"
                    routine={comparison.diff.left}
                    view={view}
                    zoom={ZOOMS[zoomIdx]}
                  />
                  <DiffPanel
                    side="right"
                    routine={comparison.diff.right}
                    view={view}
                    zoom={ZOOMS[zoomIdx]}
                  />
                </div>

                <ChangeTable rows={comparison.changes} />
              </>
            )}
          </div>

          <aside className="page-rail">
            <CommentsCard comments={comparison?.comments ?? []} />
            <SymbolsCard symbols={comparison?.symbols ?? []} />
            <FilesCard files={comparison?.files ?? []} />
            {comparison && (
              <div className="rail-actions">
                <button className="btn btn-approve btn-block">Approve comparison</button>
                <button className="btn btn-outline btn-block">Create change request</button>
              </div>
            )}
          </aside>
          </div>
        </div>
      </div>
  );
}

// ---- Controls bar ----
function Selector({
  label,
  icon,
  value,
  placeholder,
}: {
  label: string;
  icon: React.ReactNode;
  value?: string;
  placeholder: string;
}) {
  return (
    <div className="cmp-field">
      <span className="cmp-field-label">{label}</span>
      <button className="cmp-select" type="button">
        <span className="cmp-select-ico">{icon}</span>
        <span className={value ? "cmp-select-val" : "cmp-select-ph"}>
          {value ?? placeholder}
        </span>
        <ChevronDown size={15} strokeWidth={1.8} className="cmp-select-caret" />
      </button>
    </div>
  );
}

function CompareBar({ c }: { c: Comparison | null }) {
  const leftVal = c ? `${c.left.ref} @ ${c.left.version}` : undefined;
  const rightVal = c ? `${c.right.ref} @ ${c.right.version}` : undefined;
  return (
    <div className="cmp-bar">
      <Selector
        label="Repository"
        icon={<Box size={15} strokeWidth={2} />}
        value={c?.repository}
        placeholder="Select repository"
      />
      <Selector
        label="Controller"
        icon={<Cpu size={15} strokeWidth={1.8} />}
        value={c?.controller}
        placeholder="Any controller"
      />
      <Selector
        label="Left (Current)"
        icon={<GitBranch size={15} strokeWidth={1.8} />}
        value={leftVal}
        placeholder="Select reference"
      />
      <button className="cmp-swap" aria-label="Swap sides" type="button">
        <ArrowLeftRight size={15} strokeWidth={2} />
      </button>
      <Selector
        label="Right (Proposed)"
        icon={<GitBranch size={15} strokeWidth={1.8} />}
        value={rightVal}
        placeholder="Select reference"
      />
    </div>
  );
}

// ---- Summary cards ----
function SummaryCards({ c }: { c: Comparison }) {
  const s = c.summary;
  return (
    <div className="cmp-summary">
      <div className="cmp-card">
        <span className="cmp-ico red">
          <ArrowLeftRight size={18} strokeWidth={2} />
        </span>
        <div className="cmp-card-body">
          <div className="cmp-num">{s.rungsChanged}</div>
          <div className="cmp-card-label">Rungs changed</div>
          <div className="cmp-card-sub">
            <span className="t-mod">{s.rungsModified} modified</span>
            <span className="t-add">{s.rungsAdded} added</span>
            <span className="t-rem">{s.rungsRemoved} removed</span>
          </div>
        </div>
      </div>
      <div className="cmp-card">
        <span className="cmp-ico green">
          <CirclePlus size={18} strokeWidth={2} />
        </span>
        <div className="cmp-card-body">
          <div className="cmp-num">{s.networksAdded}</div>
          <div className="cmp-card-label">Networks added</div>
          <div className="cmp-card-sub">
            <span className="t-add">+{s.instructionsAdded} instructions</span>
          </div>
        </div>
      </div>
      <div className="cmp-card">
        <span className="cmp-ico blue">
          <MessageSquare size={18} strokeWidth={2} />
        </span>
        <div className="cmp-card-body">
          <div className="cmp-num">{s.commentsUpdated}</div>
          <div className="cmp-card-label">Comments updated</div>
        </div>
      </div>
      <div className="cmp-card">
        <span className="cmp-ico orange">
          <CircleAlert size={18} strokeWidth={2} />
        </span>
        <div className="cmp-card-body">
          <div className="cmp-num">{s.safetyImpacting}</div>
          <div className="cmp-card-label">Safety-impacting changes</div>
          <div className="cmp-card-sub">
            <span className="t-rem">Review required</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- Diff panel ----
function DiffPanel({
  side,
  routine,
  view,
  zoom,
}: {
  side: "left" | "right";
  routine: RoutineSide;
  view: "ladder" | "text";
  zoom: number;
}) {
  return (
    <section className={`diff-panel diff-${side}`}>
      <header className="diff-panel-head">
        <span className="dph-ref">{routine.ref}</span>
        <span className={`dph-ver ${side === "right" ? "green" : "gray"}`}>
          {routine.version}
        </span>
      </header>
      <div className="diff-panel-body" style={{ zoom }}>
        {view === "ladder" ? (
          routine.rungs.map((r) => (
            <RungView key={r.number} rung={r} showNumbers showHighlight />
          ))
        ) : (
          <div className="diff-text">
            {routine.rungs.map((r) => (
              <div key={r.number} className={`txt-rung rung-${r.state}`}>
                <span className="txt-num">{r.number}</span>
                <span className="txt-body">
                  {r.elements
                    .map((e) => `${e.tag} (${e.address})`)
                    .join("  —  ")}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

// ---- Change table ----
const KIND_META: Record<ChangeKind, { cls: string; label: string; Icon: typeof Plus }> = {
  added: { cls: "add", label: "Added", Icon: Plus },
  modified: { cls: "mod", label: "Modified", Icon: Pencil },
  removed: { cls: "rem", label: "Removed", Icon: Minus },
};
const IMPACT_META: Record<Impact, { cls: string; label: string }> = {
  low: { cls: "green", label: "Low" },
  medium: { cls: "orange", label: "Medium" },
  high: { cls: "red", label: "High" },
};

function ChangeTable({ rows }: { rows: ChangeRow[] }) {
  return (
    <div className="table-wrap cmp-table">
      <div className="cmp-table-head">
        <span className="cmp-table-title">
          Change summary <span className="cmp-table-count">{rows.length}</span>
        </span>
        <button className="btn btn-outline btn-sm">
          <Download size={15} strokeWidth={1.8} />
          Download report
        </button>
      </div>
      <div className="dtable-scroll"><table className="dtable">
        <thead>
          <tr>
            <th>Type</th>
            <th>Network</th>
            <th>Change</th>
            <th>Description</th>
            <th>Impact</th>
            <th>Author</th>
            <th aria-label="When" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const k = KIND_META[r.kind];
            const im = IMPACT_META[r.impact];
            return (
              <tr key={i}>
                <td>
                  <span className={`type-tag ${k.cls}`}>
                    <span className="type-ico">
                      <k.Icon size={12} strokeWidth={2.4} />
                    </span>
                    {k.label}
                  </span>
                </td>
                <td className="muted-cell">{r.network}</td>
                <td>
                  <span className="cmp-change">{r.change}</span>
                </td>
                <td className="cmp-desc">{r.description}</td>
                <td>
                  <span className="impact">
                    <span className={`impact-dot ${im.cls}`} />
                    {im.label}
                  </span>
                </td>
                <td>
                  <span className="author">
                    <span className="author-av">{initials(r.author)}</span>
                    {r.author}
                  </span>
                </td>
                <td className="muted-cell when-cell">{timeAgo(r.at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table></div>
    </div>
  );
}

// ---- Right rail ----
function CommentsCard({ comments }: { comments: ReviewComment[] }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Review &amp; comments</span>
        <button className="link-btn">
          <Plus size={13} strokeWidth={2} />
          Add comment
        </button>
      </div>
      {comments.length === 0 ? (
        <div className="rail-empty">No comments yet.</div>
      ) : (
        <div className="cmt-list">
          {comments.map((c, i) => (
            <div className="cmt" key={i}>
              <div className="cmt-top">
                <span className="cmt-av">{initials(c.author)}</span>
                <span className="cmt-who">{c.author}</span>
                <span className="cmt-time">{timeAgo(c.at)}</span>
              </div>
              <p className="cmt-body">{c.body}</p>
              {!c.resolved && <button className="link-btn">Resolve</button>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function SymbolsCard({ symbols }: { symbols: string[] }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Symbols affected ({symbols.length})</span>
        {symbols.length > 0 && <button className="link-btn">View all</button>}
      </div>
      {symbols.length === 0 ? (
        <div className="rail-empty">None.</div>
      ) : (
        <div className="sym-chips">
          {symbols.map((s) => (
            <span className="sym-chip" key={s}>
              {s}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function FilesCard({ files }: { files: { name: string; detail: string }[] }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Files affected ({files.length})</span>
      </div>
      {files.length === 0 ? (
        <div className="rail-empty">None.</div>
      ) : (
        <div className="file-list">
          {files.map((f) => (
            <div className="file-row" key={f.name}>
              <span className="file-ico">
                <FileCode2 size={15} strokeWidth={1.8} />
              </span>
              <div className="file-main">
                <div className="file-name">{f.name}</div>
                <div className="file-detail">{f.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function EmptyCompare() {
  return (
    <div className="empty-state">
      <span className="empty-ico">
        <ArrowLeftRight size={24} strokeWidth={1.6} />
      </span>
      <h3>Select two references to compare</h3>
      <p>Choose a repository and two branches or releases to see a logic diff.</p>
    </div>
  );
}
