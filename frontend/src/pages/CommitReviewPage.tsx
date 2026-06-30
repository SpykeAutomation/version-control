import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowRight,
  Clock,
  Copy,
  FileCode2,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequestArrow,
  Hash,
  Minus,
  MoreVertical,
  Plus,
  RotateCcw,
} from "lucide-react";
import {
  RoutineLadderDiffView,
  RoutineLadderFullView,
} from "../components/LadderDiff";
import { ProjectTree, type RoutineSelection } from "../components/ProjectTree";
import { ApiError } from "../api/client";
import type { ProjectTree as ProjectTreeData, TreeNode } from "../api/tree";
import {
  routineKey,
  type CommitDetail,
  type CommitFileStat,
  type RoutineFull,
} from "../api/commit";
import type {
  MRCodeDiff,
  MRComment,
  PRFile,
  PRRoutineChange,
} from "../api/mergeRequest";
import {
  errorText,
  useCommit,
  useProject,
  useRoutineContent,
} from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { formatDate, timeAgo } from "../lib/time";

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function CommitReviewPage() {
  const { slug, sha } = useParams();
  const { project, isPending: projectPending, error: projectError } =
    useProject(slug);
  const commitQuery = useCommit(slug, sha);

  const commit = commitQuery.data ?? null;
  const loading = (projectPending && !commit) || commitQuery.isPending;
  const notFound =
    commitQuery.error instanceof ApiError && commitQuery.error.status === 404;
  const projectFatal = Boolean(projectError);
  const error = projectFatal
    ? errorText(projectError, "Failed to load commit.")
    : commitQuery.error && !notFound
      ? errorText(commitQuery.error, "Failed to load commit.")
      : null;

  return (
      <div className="app-scroll">
        {error ? (
          <div className="page-pad">
            <div className="panel-msg error">{error}</div>
          </div>
        ) : loading ? (
          <div className="page-pad">
            <div className="panel-msg">Loading commit…</div>
          </div>
        ) : !commit ? (
          <div className="page-pad">
            <EmptyCommit slug={slug} />
          </div>
        ) : (
          <CommitReviewView
            commit={commit}
            projectName={project?.name}
            slug={slug}
            projectId={project?.id}
          />
        )}
      </div>
  );
}

// Presentational commit view, independent of data loading.
function CommitReviewView({
  commit,
  projectName,
  slug,
  projectId,
}: {
  commit: CommitDetail;
  projectName?: string;
  slug?: string;
  projectId?: number;
}) {
  const [showNumbers, setShowNumbers] = useState(true);
  const [zoom, setZoom] = useState(100);
  // The tab strip switches the main view: "changes" shows the per-file diffs;
  // "files" shows the whole-project tree with a routine viewer.
  const [tab, setTab] = useState<"changes" | "files">("changes");
  // Locally-added comments. There's no commit-comments backend endpoint yet, so
  // new comments live in component state and reset when the commit changes.
  const [added, setAdded] = useState<MRComment[]>([]);
  useEffect(() => setAdded([]), [commit.sha]);
  const comments = [...commit.comments, ...added];

  // The "Comments" tab scrolls down to the discussion rather than switching view.
  const discussionRef = useRef<HTMLElement>(null);
  const scrollToDiscussion = () =>
    discussionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  // Files-tab selection lives here (not inside FilesBrowser) so it survives
  // switching to the Changes tab and back. Resets to the first changed routine
  // when the commit changes.
  const firstChanged = useMemo(
    () => firstChangedRoutine(commit.tree.root),
    [commit.tree],
  );
  const [filesSel, setFilesSel] = useState<RoutineSelection | null>(firstChanged);
  const [filesEntity, setFilesEntity] = useState<TreeNode | null>(null);
  useEffect(() => {
    setFilesSel(firstChanged);
    setFilesEntity(null);
  }, [firstChanged]);

  return (
    <div className="mr-page">
      <nav className="crumb">
        <Link to="/projects">Repositories</Link>
        <span className="crumb-sep">/</span>
        {projectName ? (
          <Link to={`/projects/${slug}`}>{projectName}</Link>
        ) : (
          <span>Repository</span>
        )}
        <span className="crumb-sep">/</span>
        <span>Commit</span>
      </nav>

      <CommitHeader commit={commit} />
      <MetaRow commit={commit} />

      <div className={`repo-grid mr-grid${tab === "files" ? " cm-grid-full" : ""}`}>
        <div className="repo-col">
          <OverviewCard commit={commit} />
          <Tabs
            commit={commit}
            activeTab={tab}
            onChangesClick={() => setTab("changes")}
            onFilesClick={() => setTab("files")}
            onCommentsClick={scrollToDiscussion}
          />

          {tab === "changes" ? (
            <>
              <ChangesToolbar
                count={commit.files.length}
                showNumbers={showNumbers}
                onToggle={() => setShowNumbers((v) => !v)}
                zoom={zoom}
                onZoom={setZoom}
              />
              {commit.files.map((file, i) => (
                <FileSection
                  key={i}
                  index={i + 1}
                  file={file}
                  showNumbers={showNumbers}
                  zoom={zoom}
                />
              ))}
            </>
          ) : (
            <FilesBrowser
              tree={commit.tree}
              files={commit.files}
              fullContent={commit.fullContent}
              projectId={projectId}
              sha={commit.sha}
              showNumbers={showNumbers}
              onToggleNumbers={() => setShowNumbers((v) => !v)}
              selected={filesSel}
              entity={filesEntity}
              onSelectRoutine={(s) => {
                setFilesEntity(null);
                setFilesSel(s);
              }}
              onSelectEntity={(n) => {
                setFilesSel(null);
                setFilesEntity(n);
              }}
              onClear={() => {
                setFilesSel(null);
                setFilesEntity(null);
              }}
            />
          )}

          <Discussion
            sectionRef={discussionRef}
            comments={comments}
            onAdd={(c) => setAdded((prev) => [...prev, c])}
          />
        </div>

        {tab !== "files" && (
          <aside className="repo-rail cm-rail">
            <AboutCommitsCard />
            <FilesChangedCard files={commit.fileStats} />
            <ActionsCard slug={slug} branch={commit.branch} />
          </aside>
        )}
      </div>
    </div>
  );
}

// ---- Header ----
function CommitHeader({ commit }: { commit: CommitDetail }) {
  return (
    <header className="mr-head">
      <span className="mr-glyph cm-glyph" aria-hidden="true">
        <GitCommitHorizontal size={22} strokeWidth={1.8} />
      </span>
      <div className="mr-head-main">
        <div className="mr-title-row">
          <span className="cm-commit-word">Commit</span>
          <span className="cm-commit-sha">{commit.sha}</span>
          <h1 className="mr-title">{commit.title}</h1>
        </div>
        <p className="mr-sub">
          Commit on <span className="cm-branch-text">{commit.branch}</span> by{" "}
          {commit.author}
        </p>
      </div>
    </header>
  );
}

// ---- Meta row ----
function MetaCard({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mr-meta-card">
      <div className="mr-meta-label">
        <span className="mr-meta-ico">{icon}</span>
        {label}
      </div>
      <div className="mr-meta-val">{children}</div>
    </div>
  );
}

function MetaRow({ commit }: { commit: CommitDetail }) {
  return (
    <div className="mr-meta cm-meta">
      <MetaCard icon={<GitBranch size={14} strokeWidth={1.8} />} label="Branch">
        <span className="mr-meta-strong">{commit.branch}</span>
      </MetaCard>
      <MetaCard
        icon={<span className="mr-meta-av">{initials(commit.author)}</span>}
        label="Author"
      >
        <span className="mr-meta-strong">{commit.author}</span>
        {commit.authorRole && (
          <span className="mr-meta-sub">{commit.authorRole}</span>
        )}
      </MetaCard>
      <MetaCard icon={<Clock size={14} strokeWidth={1.8} />} label="Date">
        <span className="mr-meta-strong">{timeAgo(commit.authoredAt)}</span>
        <span className="mr-meta-sub">{formatDate(commit.authoredAt)}</span>
      </MetaCard>
      <MetaCard
        icon={<GitCommitHorizontal size={14} strokeWidth={1.8} />}
        label="Parent commit"
      >
        <span className="mr-meta-mono cm-link">{commit.parentSha}</span>
      </MetaCard>
      <MetaCard icon={<FileCode2 size={14} strokeWidth={1.8} />} label="Files changed">
        <span className="mr-meta-strong">{commit.filesChanged}</span>
        <span className="mr-meta-sub cm-diffstat">
          <span className="t-add">+{commit.additions}</span> /{" "}
          <span className="t-rem">−{commit.deletions}</span>
        </span>
      </MetaCard>
      <MetaCard icon={<Hash size={14} strokeWidth={1.8} />} label="Commit hash">
        <span className="cm-hash-row">
          <span className="mr-meta-mono">{commit.sha}</span>
          <button
            className="cm-copy"
            type="button"
            aria-label="Copy commit hash"
            onClick={() => navigator.clipboard?.writeText(commit.sha)}
          >
            <Copy size={13} strokeWidth={1.9} />
          </button>
        </span>
      </MetaCard>
    </div>
  );
}

// ---- Overview: message + summary + stats ----
function OverviewCard({ commit }: { commit: CommitDetail }) {
  return (
    <section className="cm-overview">
      <div className="cm-ov-block">
        <div className="cm-ov-label">Commit message</div>
        <p className="cm-ov-message">{commit.message}</p>
      </div>
      <div className="cm-ov-block cm-ov-summary">
        <div className="cm-ov-label">Commit summary</div>
        {commit.summary.length > 0 ? (
          <ul className="cm-ov-list">
            {commit.summary.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        ) : (
          <p className="cm-ov-message muted">No summary provided.</p>
        )}
      </div>
    </section>
  );
}

// ---- Tabs ----
function Tabs({
  commit,
  activeTab,
  onChangesClick,
  onFilesClick,
  onCommentsClick,
}: {
  commit: CommitDetail;
  activeTab: "changes" | "files";
  onChangesClick: () => void;
  onFilesClick: () => void;
  onCommentsClick: () => void;
}) {
  const tabs: { key: string; label: string; count?: number }[] = [
    { key: "changes", label: "Changes" },
    { key: "files", label: "Files" },
    { key: "comments", label: "Comments", count: commit.comments.length },
  ];
  // "Changes" / "Files" switch the view; "Comments" scrolls to the discussion.
  const handlers: Record<string, (() => void) | undefined> = {
    changes: onChangesClick,
    files: onFilesClick,
    comments: onCommentsClick,
  };
  return (
    <nav className="pr-tabs cm-tabs">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`pr-tab${t.key === activeTab ? " active" : ""}`}
          type="button"
          onClick={handlers[t.key]}
        >
          {t.label}
          {t.count != null && <span className="pr-tab-count">{t.count}</span>}
        </button>
      ))}
    </nav>
  );
}

// ---- Files tab: project tree + routine viewer ----
// The first changed routine in the tree, used as the default selection so the
// viewer opens on something meaningful rather than empty.
function firstChangedRoutine(node: TreeNode): RoutineSelection | null {
  if (node.kind === "routine" && node.status !== "unchanged" && node.routine) {
    return {
      controller: node.controller ?? "",
      program: node.program ?? "",
      routine: node.routine,
      routineType: node.routine_type,
    };
  }
  for (const child of node.children) {
    const found = firstChangedRoutine(child);
    if (found) return found;
  }
  return null;
}

// Find the tree node for a selection, so the viewer can read the routine's real
// change status (added / removed / modified / unchanged).
function findRoutineNode(node: TreeNode, sel: RoutineSelection): TreeNode | null {
  if (
    node.kind === "routine" &&
    node.routine === sel.routine &&
    (node.program ?? "") === (sel.program ?? "") &&
    (node.controller ?? "") === (sel.controller ?? "")
  ) {
    return node;
  }
  for (const child of node.children) {
    const found = findRoutineNode(child, sel);
    if (found) return found;
  }
  return null;
}

// Placeholder text for a selected routine that has no renderable diff: an
// unchanged routine, or (against a real backend) a changed routine whose diff
// isn't carried in this view yet.
function routinePlaceholder(name: string, status?: TreeNode["status"]) {
  const strong = <strong>{name}</strong>;
  if (status === "added") {
    return <>{strong} was added in this commit. A full routine view isn't available here yet.</>;
  }
  if (status === "removed") {
    return <>{strong} was removed in this commit.</>;
  }
  if (status === "modified") {
    return <>{strong} changed in this commit, but its diff isn't available in this view yet.</>;
  }
  return (
    <>
      {strong} is unchanged in this commit. This view shows changed routines; full
      routine viewing isn't available yet.
    </>
  );
}

function FilesBrowser({
  tree,
  files,
  fullContent,
  projectId,
  sha,
  showNumbers,
  onToggleNumbers,
  selected,
  entity,
  onSelectRoutine,
  onSelectEntity,
  onClear,
}: {
  tree: ProjectTreeData;
  files: PRFile[];
  fullContent: Record<string, RoutineFull>;
  projectId?: number;
  sha: string;
  showNumbers: boolean;
  onToggleNumbers: () => void;
  selected: RoutineSelection | null;
  entity: TreeNode | null;
  onSelectRoutine: (sel: RoutineSelection) => void;
  onSelectEntity: (node: TreeNode) => void;
  onClear: () => void;
}) {
  const selNode = selected ? findRoutineNode(tree.root, selected) : null;

  // Resolve the diff to render by full identity (controller + program + routine),
  // not name alone, so same-named routines in different programs don't collide.
  // When a routine carries more than one kind of change, prefer the one matching
  // the tree node's language.
  const byName = selected
    ? files.flatMap((f) => f.changes).filter((c) => c.routine === selected.routine)
    : [];
  // Prefer changes whose program/controller exactly match the selection. Only
  // fall back to name-only matches when the selection itself has no program —
  // otherwise a change with a null program would wrongly claim a same-named
  // routine in another program.
  const exact = selected
    ? byName.filter(
        (c) =>
          (c.program ?? null) === (selected.program || null) &&
          (c.controller ?? null) === (selected.controller || null),
      )
    : [];
  const pool = exact.length ? exact : selected?.program ? [] : byName;
  const wantKind =
    selected?.routineType === "st"
      ? "structured"
      : selected?.routineType === "rll"
        ? "ladder"
        : undefined;
  const change =
    (wantKind ? pool.find((c) => c.kind === wantKind) : undefined) ?? pool[0];

  return (
    <>
      <div className="pr-changes-bar">
        <span className="pr-changes-title">Project files</span>
        <label className="mr-toggle">
          <input type="checkbox" checked={showNumbers} onChange={onToggleNumbers} />
          Show rung numbers
        </label>
      </div>
      <div className="commit-tree-diff">
        <aside className="tree-rail">
          <ProjectTree
            root={tree.root}
            selected={selected}
            onSelectRoutine={onSelectRoutine}
            onSelectEntity={onSelectEntity}
            onClear={onClear}
          />
        </aside>
        <div className="commit-diff-stage">
          {entity && !selected ? (
            <div className="rcard-empty">
              <strong>{entity.label}</strong>{" "}
              {entity.status === "unchanged"
                ? "is unchanged in this commit."
                : "changed in this commit."}{" "}
              Detail for non-routine items isn't shown in this view.
            </div>
          ) : !selected ? (
            <div className="rcard-empty">
              Select a routine from the tree to view it.
            </div>
          ) : change?.kind === "ladder" && change.ladder ? (
            <div className="mr-ladderwrap">
              <RoutineLadderDiffView
                routine={change.ladder}
                showNumbers={showNumbers}
              />
            </div>
          ) : change?.code ? (
            <CodeDiffBody diff={change.code} />
          ) : (
            <FullRoutineViewer
              projectId={projectId}
              sha={sha}
              selection={selected}
              embedded={fullContent[routineKey(selected.program, selected.routine)]}
              status={selNode?.status}
              showNumbers={showNumbers}
            />
          )}
        </div>
      </div>
    </>
  );
}

// Renders a routine in full when it has no diff to show: uses content already
// carried with the commit when present, otherwise fetches it from the backend.
// Falls back to a status-aware placeholder while loading or when no content is
// available (e.g. the backend endpoint isn't there yet).
function FullRoutineViewer({
  projectId,
  sha,
  selection,
  embedded,
  status,
  showNumbers,
}: {
  projectId?: number;
  sha: string;
  selection: RoutineSelection;
  embedded?: RoutineFull;
  status?: TreeNode["status"];
  showNumbers: boolean;
}) {
  // Only hit the backend when the content isn't already carried with the commit.
  const query = useRoutineContent(
    projectId,
    sha,
    selection.program,
    selection.routine,
    !embedded,
  );
  const content = embedded ?? query.data;

  if (content) {
    return content.kind === "ladder" ? (
      <div className="mr-ladderwrap">
        <RoutineLadderFullView routine={content.ladder} showNumbers={showNumbers} />
      </div>
    ) : (
      <RoutineCodeFullView refLabel={content.ref} lines={content.lines} />
    );
  }
  // isFetching (not isPending) — a disabled query stays "pending" in v5, which
  // would otherwise leave this stuck on "Loading…" and never fall through.
  if (query.isFetching) {
    return <div className="rcard-empty">Loading {selection.routine}…</div>;
  }
  return (
    <div className="rcard-empty">
      {routinePlaceholder(selection.routine, status)}
    </div>
  );
}

// A whole structured-text routine, read-only (single column, no diff markers).
function RoutineCodeFullView({
  refLabel,
  lines,
}: {
  refLabel: string;
  lines: { ln: number; text: string }[];
}) {
  return (
    <div className="cmfull">
      <div className="cmfull-head">
        <span className="sxs-head-ver">{refLabel}</span>
      </div>
      <div className="cmfull-body">
        {lines.map((l, i) => (
          <div className="cd-line" key={i}>
            <span className="cd-num">{l.ln}</span>
            <span className="cd-code">{highlightST(l.text, "right")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- Changes, grouped by file ----
// Toolbar above the changed-file list: file count on the left, diff controls
// (rung numbers, zoom) on the right — they apply to every diff below.
function ChangesToolbar({
  count,
  showNumbers,
  onToggle,
  zoom,
  onZoom,
}: {
  count: number;
  showNumbers: boolean;
  onToggle: () => void;
  zoom: number;
  onZoom: (z: number) => void;
}) {
  return (
    <div className="pr-changes-bar">
      <span className="pr-changes-title">
        Changed files
        <span className="mr-section-count">{count}</span>
      </span>
      <div className="mr-section-tools">
        <label className="mr-toggle">
          <input type="checkbox" checked={showNumbers} onChange={onToggle} />
          Show rung numbers
        </label>
        <ZoomControl zoom={zoom} onZoom={onZoom} />
      </div>
    </div>
  );
}

// One changed file: a header naming the file, then each routine that changed
// inside it (ladder and/or structured text).
function FileSection({
  index,
  file,
  showNumbers,
  zoom,
}: {
  index: number;
  file: PRFile;
  showNumbers: boolean;
  zoom: number;
}) {
  return (
    <section className="mr-section pr-file">
      <div className="mr-section-head">
        <div className="mr-section-title">
          <span className="mr-section-num">{index}.</span>
          <span className="pr-file-ico">
            <FileCode2 size={15} strokeWidth={1.8} />
          </span>
          <span className="pr-file-name">{file.name}</span>
          <span className="mr-section-count">
            {file.changes.length}{" "}
            {file.changes.length === 1 ? "routine" : "routines"}
          </span>
        </div>
      </div>
      <div className="pr-file-body" style={{ zoom: zoom / 100 }}>
        {file.changes.map((ch, i) => (
          <RoutineChangeBlock key={i} change={ch} showNumbers={showNumbers} />
        ))}
      </div>
    </section>
  );
}

// One routine's change within a file: a quiet sub-header (routine name), then
// the diff drawn by the matching renderer.
function RoutineChangeBlock({
  change,
  showNumbers,
}: {
  change: PRRoutineChange;
  showNumbers: boolean;
}) {
  return (
    <div className="pr-routine">
      <div className="pr-routine-head">
        <span className="pr-routine-name">{change.routine}</span>
      </div>
      {change.kind === "ladder" && change.ladder ? (
        <div className="mr-ladderwrap">
          <RoutineLadderDiffView routine={change.ladder} showNumbers={showNumbers} />
        </div>
      ) : change.code ? (
        <CodeDiffBody diff={change.code} />
      ) : null}
    </div>
  );
}

function ZoomControl({
  zoom,
  onZoom,
}: {
  zoom: number;
  onZoom: (z: number) => void;
}) {
  return (
    <div className="zoom cm-zoom">
      <span className="zoom-word">Zoom:</span>
      <button
        className="zoom-btn"
        type="button"
        aria-label="Zoom out"
        onClick={() => onZoom(Math.max(50, zoom - 10))}
      >
        <Minus size={14} strokeWidth={2} />
      </button>
      <span className="zoom-val">{zoom}%</span>
      <button
        className="zoom-btn"
        type="button"
        aria-label="Zoom in"
        onClick={() => onZoom(Math.min(200, zoom + 10))}
      >
        <Plus size={14} strokeWidth={2} />
      </button>
    </div>
  );
}

// ---- Structured-text diff ----
const ST_KEYWORDS = new Set([
  "IF", "THEN", "ELSE", "ELSIF", "END_IF", "AND", "OR", "NOT", "TRUE", "FALSE",
  "RETURN", "FOR", "TO", "DO", "WHILE", "END_FOR", "END_WHILE", "CASE", "OF",
  "END_CASE", "XOR", "MOD",
]);

// Lightweight ST highlighter. Tokens wrapped in ⟦…⟧ are the changed value on
// this side (green on the right, red on the left); known keywords render in the
// accent colour; everything else is plain text. Mirrors the merge-request page.
function highlightST(text: string, side: "left" | "right"): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const changeCls = side === "right" ? "tok-add" : "tok-rem";
  const parts = text.split(/(⟦[^⟧]*⟧)/g);
  let key = 0;
  for (const part of parts) {
    if (!part) continue;
    if (part.startsWith("⟦") && part.endsWith("⟧")) {
      out.push(
        <span className={changeCls} key={key++}>
          {part.slice(1, -1)}
        </span>,
      );
      continue;
    }
    const toks = part.split(/(\b[A-Za-z_][A-Za-z0-9_]*\b)/g);
    for (const tok of toks) {
      if (!tok) continue;
      if (ST_KEYWORDS.has(tok)) {
        out.push(
          <span className="tok-kw" key={key++}>
            {tok}
          </span>,
        );
      } else {
        out.push(<span key={key++}>{tok}</span>);
      }
    }
  }
  return out;
}

// Structured-text diff. Uses the same markup as the merge-request page
// (.mr-sxs / dark headers / token highlighting) so the two pages' diffs match.
function CodeDiffBody({ diff }: { diff: MRCodeDiff }) {
  const rows = Math.max(diff.left.lines.length, diff.right.lines.length);
  const last = rows - 1;
  return (
    <div className="pr-codewrap">
      <div className="mr-sxs mr-sxs-code">
        <div className="sxs-head sxs-head-l">
          <span className="sxs-head-ver">{diff.left.ref}</span>
        </div>
        <div className="sxs-head sxs-gut" />
        <div className="sxs-head sxs-head-r">
          <span className="sxs-head-ver">{diff.right.ref}</span>
        </div>
        {Array.from({ length: rows }).map((_, i) => {
          const l = diff.left.lines[i];
          const r = diff.right.lines[i];
          const edge = i === last ? " sxs-last" : "";
          return (
            <div className="sxs-row" key={i} style={{ display: "contents" }}>
              <div className={`sxs-cell sxs-l${edge}`}>
                {l && (
                  <div className="cd-line">
                    <span className="cd-num">{l.ln}</span>
                    <span className="cd-code">{highlightST(l.text, "left")}</span>
                  </div>
                )}
              </div>
              <div className="sxs-gut" />
              <div className={`sxs-cell sxs-r${edge}`}>
                {r && (
                  <div className="cd-line">
                    <span className="cd-num">{r.ln}</span>
                    <span className="cd-code">{highlightST(r.text, "right")}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---- Discussion ----
function Discussion({
  comments,
  onAdd,
  sectionRef,
}: {
  comments: MRComment[];
  onAdd: (comment: MRComment) => void;
  sectionRef?: React.Ref<HTMLElement>;
}) {
  return (
    <section className="mr-section" ref={sectionRef} style={{ scrollMarginTop: 12 }}>
      <div className="mr-section-head">
        <div className="mr-section-title">
          Discussion
          <span className="mr-section-count">{comments.length} comments</span>
        </div>
      </div>
      <div className="disc-list">
        {comments.length === 0 && (
          <div className="rail-empty">No comments yet.</div>
        )}
        {comments.map((c, i) => (
          <article className="disc-item" key={i}>
            <span className="disc-av">{initials(c.author)}</span>
            <div className="disc-main">
              <div className="disc-content">
                <div className="disc-top">
                  <span className="disc-who">{c.author}</span>
                  <span className="disc-role">{c.role}</span>
                  {c.on && <span className="disc-on">Comment on {c.on}</span>}
                </div>
                <p className="disc-body">{c.body}</p>
              </div>
              <div className="disc-aside">
                <div className="disc-aside-top">
                  <span className="disc-time">{timeAgo(c.at)}</span>
                  <button className="disc-kebab" type="button" aria-label="More" disabled title="Coming soon">
                    <MoreVertical size={15} strokeWidth={2} />
                  </button>
                </div>
              </div>
            </div>
          </article>
        ))}
        <DiscussionComposer onAdd={onAdd} />
      </div>
    </section>
  );
}

// Comment composer at the foot of the discussion. There's no commit-comments
// backend endpoint yet, so a posted comment is added to the local thread (it
// shows immediately but isn't persisted across reloads).
function DiscussionComposer({ onAdd }: { onAdd: (comment: MRComment) => void }) {
  const { user } = useAuth();
  const [body, setBody] = useState("");
  const name = user?.name ?? "You";
  const canSubmit = body.trim().length > 0;

  const submit = () => {
    if (!canSubmit) return;
    onAdd({
      author: name,
      role: "You",
      isAuthor: true,
      at: new Date().toISOString(),
      body: body.trim(),
    });
    setBody("");
  };

  return (
    <div className="disc-composer">
      <span className="disc-av">{initials(name)}</span>
      <div className="disc-composer-main">
        <textarea
          className="textarea tall"
          placeholder="Add a comment…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="disc-composer-actions">
          <button
            className="btn btn-primary btn-sm"
            type="button"
            disabled={!canSubmit}
            onClick={submit}
          >
            Comment
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Right rail ----
function AboutCommitsCard() {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">About commits</span>
      </div>
      <div className="about-body">
        <p className="about-intro">
          The commit view shows a single commit's changes against its parent.
        </p>
        <div className="about-item">
          <span className="about-ico">
            <GitCommitHorizontal size={16} strokeWidth={1.9} />
          </span>
          <div>
            <div className="about-item-title">Commits</div>
            <div className="about-item-desc">
              A saved snapshot of the project. It records what changed in the
              logic, who made the change, and when.
            </div>
          </div>
        </div>
        <div className="about-item">
          <span className="about-ico">
            <RotateCcw size={16} strokeWidth={1.9} />
          </span>
          <div>
            <div className="about-item-title">Reverting</div>
            <div className="about-item-desc">
              Commits are read-only history. To undo one, revert it — that adds a
              new commit restoring the earlier state.
            </div>
          </div>
        </div>
        <Link to="/documentation" className="about-docs">
          Go to docs
          <ArrowRight size={14} strokeWidth={2} />
        </Link>
      </div>
    </section>
  );
}

function FilesChangedCard({ files }: { files: CommitFileStat[] }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Files changed ({files.length})</span>
      </div>
      {files.length === 0 ? (
        <div className="rail-empty">No files changed.</div>
      ) : (
        <>
          <div className="cm-files">
            {files.map((f) => (
              <div className="cm-file-row" key={f.name}>
                <FileCode2 size={14} strokeWidth={1.8} className="cm-file-ico" />
                <span className="cm-file-name">{f.name}</span>
                <span className="cm-file-stat">
                  <span className="t-add">+{f.additions}</span> /{" "}
                  <span className="t-rem">−{f.deletions}</span>
                </span>
              </div>
            ))}
          </div>
          <button className="link-btn cm-viewall" type="button">
            View all files
          </button>
        </>
      )}
    </section>
  );
}

function ActionsCard({ slug, branch }: { slug?: string; branch?: string }) {
  // Opening a change request from this commit's branch is a real flow (the
  // create-merge-request page), so this links straight to it with the branch
  // pre-selected as the source. Revert has no backend yet, so it stays disabled.
  const canCreate = Boolean(slug && branch);
  return (
    <section className="rail-section cm-actions">
      <div className="rail-head">
        <span className="rail-title">Actions</span>
      </div>
      {canCreate ? (
        <Link
          to={`/projects/${slug}/merge-requests/new?source=${encodeURIComponent(branch!)}`}
          className="btn btn-outline btn-block btn-sm"
        >
          <GitPullRequestArrow size={15} strokeWidth={1.9} />
          Create change request
        </Link>
      ) : (
        <button className="btn btn-outline btn-block btn-sm" disabled>
          <GitPullRequestArrow size={15} strokeWidth={1.9} />
          Create change request
        </button>
      )}
      <button className="btn btn-block btn-sm cm-revert" disabled title="Coming soon">
        <RotateCcw size={15} strokeWidth={1.9} />
        Revert commit
      </button>
    </section>
  );
}

function EmptyCommit({ slug }: { slug?: string }) {
  return (
    <div className="empty-state">
      <span className="empty-ico">
        <GitCommitHorizontal size={24} strokeWidth={1.6} />
      </span>
      <h3>Commit not found</h3>
      <p>We couldn't find that commit. It may have been removed or rebased away.</p>
      <Link
        to={slug ? `/projects/${slug}` : "/projects"}
        className="btn btn-primary btn-sm"
      >
        Back to repository
      </Link>
    </div>
  );
}
