import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeftRight,
  Box,
  ChevronDown,
  CircleAlert,
  CirclePlus,
  FileCode2,
  GitBranch,
  GitCommitHorizontal,
  Minus,
  Pencil,
  Plus,
  X,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { LadderDiffView } from "../components/LadderDiff";
import { ProjectTree, type RoutineSelection } from "../components/ProjectTree";
import type { TreeNode } from "../api/tree";
import {
  errorText,
  useCommitDiff,
  useCommitLadderDiff,
  useCommits,
  useCommitTree,
  useDiff,
  useLadderDiff,
  useTree,
  useProject,
} from "../api/queries";
import type { Commit } from "../api/repository";
import {
  deriveChangeView,
  type ChangeRow,
  type ChangeRowKind,
  type ChangeSummary,
} from "../lib/changeset";
import { formatDate } from "../lib/time";

// Element scale is controlled intrinsically in CSS (font/box sizes), not with a
// `zoom`/transform on the stage — those shrink the footprint too, which would
// leave the diff hugging the left and wasting the page's horizontal space.

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function CommitDetailPage() {
  const { slug, sha } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { isPending: projectPending, error: projectError, project } =
    useProject(slug);

  const shortSha = sha ? sha.slice(0, 7) : "";
  // The Left selector can pick a base other than the parent; it lives in the URL
  // (?base=) so the comparison is shareable. With no explicit base we diff
  // against the parent, which also handles the very first commit.
  const explicitBase = searchParams.get("base") || undefined;
  const genBase = explicitBase ? explicitBase.slice(0, 7) : undefined;

  // Both fetch strategies' hooks always run (rules of hooks); the unused pair is
  // turned off by its `enabled` guard. Default is commit-vs-parent; an explicit
  // base switches to a generic base→head diff.
  const cvpDiff = useCommitDiff(project?.id, explicitBase ? undefined : sha);
  const cvpLadder = useCommitLadderDiff(project?.id, explicitBase ? undefined : sha);
  const cvpTree = useCommitTree(project?.id, explicitBase ? undefined : sha);
  const genDiff = useDiff(project?.id, genBase, explicitBase ? shortSha : undefined);
  const genLadder = useLadderDiff(project?.id, genBase, explicitBase ? shortSha : undefined);
  const genTree = useTree(project?.id, genBase, explicitBase ? shortSha : undefined);
  const diffQuery = explicitBase ? genDiff : cvpDiff;
  const ladderQuery = explicitBase ? genLadder : cvpLadder;
  const treeQuery = explicitBase ? genTree : cvpTree;

  // Tree selection. A routine filters the ladder diff to just that routine; any
  // other changed node focuses its change-summary rows. They are mutually
  // exclusive — picking one clears the other.
  const [routineSel, setRoutineSel] = useState<RoutineSelection | null>(null);
  const [entitySel, setEntitySel] = useState<TreeNode | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);
  // Switching commits should drop any prior selection.
  useEffect(() => {
    setRoutineSel(null);
    setEntitySel(null);
  }, [sha, explicitBase]);
  // A non-routine pick has no ladder card, so bring its change rows into view.
  useEffect(() => {
    if (entitySel) tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [entitySel]);

  const selectRoutine = (sel: RoutineSelection) => {
    setEntitySel(null);
    setRoutineSel(sel);
  };
  const selectEntity = (node: TreeNode) => {
    setRoutineSel(null);
    setEntitySel(node);
  };
  const clearSelection = () => {
    setRoutineSel(null);
    setEntitySel(null);
  };

  // The commit's message/author/date aren't on the diff endpoints, so we look
  // them up in the branch's commit list and match on the full sha.
  const defaultBranch = project?.branches[0] ?? "main";
  const branch = defaultBranch;
  const commits = useCommits(project?.id, branch).data ?? null;
  const meta = commits?.find((c) => c.sha === sha) ?? null;

  const changeView = diffQuery.data ? deriveChangeView(diffQuery.data) : null;

  // Apply the tree selection to the ladder cards and the change rows. A routine
  // pick narrows both to that routine; an entity pick narrows the table to that
  // name; no pick shows everything.
  const allRoutines = ladderQuery.data?.routines ?? [];
  const visibleRoutines = routineSel
    ? allRoutines.filter(
        (r) =>
          r.controller === routineSel.controller &&
          r.program === routineSel.program &&
          r.routine === routineSel.routine,
      )
    : allRoutines;
  const filterName = routineSel?.routine ?? entitySel?.label ?? null;
  const visibleRows =
    changeView && filterName
      ? changeView.rows.filter((r) => r.name === filterName)
      : (changeView?.rows ?? []);

  // The list is newest first, so the entry after the head is its parent (the
  // default base); commits older than the head are the valid base options.
  const commitIdx = commits ? commits.findIndex((c) => c.sha === sha) : -1;
  const parent =
    commitIdx >= 0 && commits ? commits[commitIdx + 1] : undefined;
  const baseOptions =
    commitIdx >= 0 && commits ? commits.slice(commitIdx + 1) : [];
  const baseValue = explicitBase ?? parent?.sha ?? "";

  // Until the project resolves, the diff/ladder queries are disabled, and a
  // disabled React Query (v5) reports `pending`. Only count them as loading
  // once we have a project — otherwise a bad slug would hang on "Loading…"
  // instead of falling through to the not-found state.
  const loading =
    projectPending ||
    (project != null &&
      (diffQuery.isPending || ladderQuery.isPending || treeQuery.isPending));
  const error = projectError
    ? errorText(projectError, "Failed to load commit.")
    : diffQuery.error
      ? errorText(diffQuery.error, "Failed to load commit.")
      : ladderQuery.error
        ? errorText(ladderQuery.error, "Failed to load commit.")
        : treeQuery.error
          ? errorText(treeQuery.error, "Failed to load commit.")
          : null;

  return (
    <>
      <TopBar />
      <div className="app-scroll">
        {error ? (
          <div className="page-pad">
            <div className="panel-msg error">{error}</div>
          </div>
        ) : loading ? (
          <div className="page-pad">
            <div className="panel-msg">Loading commit…</div>
          </div>
        ) : !project ? (
          <div className="page-pad">
            <div className="empty-state">
              <span className="empty-ico">
                <Box size={24} strokeWidth={1.6} />
              </span>
              <h3>Repository not found</h3>
              <p>We couldn't find a project with that name.</p>
              <Link to="/projects" className="btn btn-primary btn-sm">
                Back to projects
              </Link>
            </div>
          </div>
        ) : (
          <div className="page-grid compare-grid commit-grid-tree">
            {treeQuery.data ? (
              <aside className="tree-rail">
                <ProjectTree
                  root={treeQuery.data.root}
                  selected={routineSel}
                  onSelectRoutine={selectRoutine}
                  onSelectEntity={selectEntity}
                  onClear={clearSelection}
                />
              </aside>
            ) : (
              <div />
            )}
            <div className="page-main">
              <nav className="crumb">
                <Link to="/projects">Projects</Link>
                <span className="crumb-sep">/</span>
                <Link to={`/projects/${project.slug}`}>{project.name}</Link>
                <span className="crumb-sep">/</span>
                <span>{shortSha}</span>
              </nav>

              <header className="page-header">
                <h1>{meta?.message ?? `Commit ${shortSha}`}</h1>
                <p className="commit-detail-meta">
                  <span className="hash">{shortSha}</span>
                  {meta && (
                    <>
                      <span className="author">
                        <span className="author-av">{initials(meta.author)}</span>
                        {meta.author}
                      </span>
                      <span className="muted-cell">{formatDate(meta.at)}</span>
                    </>
                  )}
                </p>
              </header>

              <CommitBar
                branches={project.branches}
                branch={branch}
                onBranchChange={(b) =>
                  navigate(`/projects/${project.slug}/tree/${b}`)
                }
                baseValue={baseValue}
                baseOptions={baseOptions}
                onBaseChange={(b) =>
                  setSearchParams(b && b !== parent?.sha ? { base: b } : {})
                }
                headValue={sha ?? ""}
                headOptions={commits ?? []}
                onHeadChange={(h) =>
                  navigate(`/projects/${project.slug}/commit/${h}`)
                }
              />

              {!changeView || changeView.rows.length === 0 ? (
                <EmptyCommit />
              ) : (
                <>
                  <SummaryCards s={changeView.summary} />

                  <FilesCard files={changeView?.files ?? []} />

                  {filterName && (
                    <div className="tree-filter-note">
                      <span>
                        Filtered to <strong>{filterName}</strong>
                      </span>
                      <button
                        type="button"
                        className="tree-filter-clear"
                        onClick={clearSelection}
                      >
                        <X size={13} strokeWidth={2} /> Show all
                      </button>
                    </div>
                  )}

                  <div className="commit-diff-stage">
                    {visibleRoutines.length > 0 ? (
                      <LadderDiffView
                        doc={{ ...ladderQuery.data!, routines: visibleRoutines }}
                        showNumbers
                      />
                    ) : routineSel ? (
                      <div className="rcard-empty">
                        <strong>{routineSel.routine}</strong> has no ladder logic to
                        diff. See the change summary below.
                      </div>
                    ) : (
                      <div className="rcard-empty">
                        No ladder logic changed in this commit. See the change
                        summary below.
                      </div>
                    )}
                  </div>

                  <div ref={tableRef}>
                    <ChangeTable rows={visibleRows} />
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// ---- Comparison context bar ----
// Mirrors the Compare page's selector bar. All three are pickers: Branch chooses
// the branch; Left is the base commit (defaults to the parent); Right is the
// commit being viewed. Changing Right navigates to that commit; changing Left
// re-bases via a ?base= query param.
function CommitBar({
  branches,
  branch,
  onBranchChange,
  baseValue,
  baseOptions,
  onBaseChange,
  headValue,
  headOptions,
  onHeadChange,
}: {
  branches: string[];
  branch: string;
  onBranchChange: (branch: string) => void;
  baseValue: string;
  baseOptions: Commit[];
  onBaseChange: (sha: string) => void;
  headValue: string;
  headOptions: Commit[];
  onHeadChange: (sha: string) => void;
}) {
  const commitOpts = (cs: Commit[]) =>
    cs.map((c) => ({ value: c.sha, label: `${c.hash} · ${c.message}` }));
  const leftOpts = baseOptions.length
    ? commitOpts(baseOptions)
    : [{ value: "", label: "initial" }];
  return (
    <div className="cmp-bar cd-bar">
      <BarSelect
        label="Branch"
        icon={<GitBranch size={15} strokeWidth={1.8} />}
        value={branch}
        options={branches.map((b) => ({ value: b, label: b }))}
        onChange={onBranchChange}
      />
      <BarSelect
        label="Left"
        icon={<GitCommitHorizontal size={15} strokeWidth={1.8} />}
        value={baseValue}
        options={leftOpts}
        onChange={onBaseChange}
        disabled={!baseOptions.length}
      />
      <BarSelect
        label="Right"
        icon={<GitCommitHorizontal size={15} strokeWidth={1.8} />}
        value={headValue}
        options={commitOpts(headOptions)}
        onChange={onHeadChange}
      />
    </div>
  );
}

function BarSelect({
  label,
  icon,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  icon: React.ReactNode;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="cmp-field">
      <span className="cmp-field-label">{label}</span>
      <div className="cmp-select">
        <span className="cmp-select-ico">{icon}</span>
        <select
          className="cmp-bare-select"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown size={15} strokeWidth={1.8} className="cmp-select-caret" />
      </div>
    </div>
  );
}

// ---- Summary cards ----
function SummaryCards({ s }: { s: ChangeSummary }) {
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
          <div className="cmp-num">{s.routinesChanged}</div>
          <div className="cmp-card-label">Routines changed</div>
          <div className="cmp-card-sub">
            <span className="t-mod">{s.programsChanged} programs</span>
          </div>
        </div>
      </div>
      <div className="cmp-card">
        <span className="cmp-ico blue">
          <FileCode2 size={18} strokeWidth={2} />
        </span>
        <div className="cmp-card-body">
          <div className="cmp-num">{s.tagsChanged}</div>
          <div className="cmp-card-label">Tags changed</div>
        </div>
      </div>
      <div className="cmp-card">
        <span className="cmp-ico orange">
          <CircleAlert size={18} strokeWidth={2} />
        </span>
        <div className="cmp-card-body">
          <div className="cmp-num">{s.entitiesChanged}</div>
          <div className="cmp-card-label">Other entities changed</div>
          <div className="cmp-card-sub">
            <span className="muted-cell">Modules, data types, AOIs, tasks</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- Change table ----
const KIND_META: Record<
  ChangeRowKind,
  { cls: string; label: string; Icon: typeof Plus }
> = {
  added: { cls: "add", label: "Added", Icon: Plus },
  modified: { cls: "mod", label: "Modified", Icon: Pencil },
  removed: { cls: "rem", label: "Removed", Icon: Minus },
};

function ChangeTable({ rows }: { rows: ChangeRow[] }) {
  return (
    <div className="table-wrap cmp-table">
      <div className="cmp-table-head">
        <span className="cmp-table-title">
          Change summary <span className="cmp-table-count">{rows.length}</span>
        </span>
      </div>
      <table className="dtable">
        <thead>
          <tr>
            <th>Type</th>
            <th>Location</th>
            <th>Name</th>
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const k = KIND_META[r.kind];
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
                <td className="muted-cell">{r.breadcrumb}</td>
                <td>
                  <span className="cmp-change">{r.name}</span>
                </td>
                <td className="cmp-desc">{r.description}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---- Right rail ----
function FilesCard({ files }: { files: string[] }) {
  return (
    <section className="rail-section commit-files">
      <div className="rail-head">
        <span className="rail-title">Files affected ({files.length})</span>
      </div>
      {files.length === 0 ? (
        <div className="rail-empty">None.</div>
      ) : (
        <div className="file-list">
          {files.map((name) => (
            <div className="file-row" key={name}>
              <span className="file-ico">
                <FileCode2 size={15} strokeWidth={1.8} />
              </span>
              <div className="file-main">
                <div className="file-name">{name}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function EmptyCommit() {
  return (
    <div className="empty-state">
      <span className="empty-ico">
        <GitCommitHorizontal size={24} strokeWidth={1.6} />
      </span>
      <h3>No changes in this commit.</h3>
      <p>This commit didn't change any PLC logic, tags, or other entities.</p>
    </div>
  );
}
