import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowRight,
  Clock,
  Copy,
  FileCode2,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequestArrow,
  Hash,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import {
  RoutineLadderDiffView,
  RoutineLadderFullView,
} from "../components/LadderDiff";
import {
  CodeDiffBody,
  FileSection,
  highlightST,
  ZoomControl,
} from "../components/ChangesView";
import { EntityPanel } from "../components/L5xPanels";
import { Discussion } from "../components/Discussion";
import { Dismissible } from "../components/Dismissible";
import { TabStrip } from "../components/Tabs";
import { ProjectTree, type RoutineSelection } from "../components/ProjectTree";
import { ApiError } from "../api/client";
import type { ProjectTree as ProjectTreeData, TreeNode } from "../api/tree";
import {
  routineKey,
  type CommitDetail,
  type CommitFileStat,
  type RoutineFull,
} from "../api/commit";
import type { ChangedFile, EntityChange } from "../api/diff";
import type { PRFile } from "../api/mergeRequest";
import {
  entityChangeGroups,
  type EntityChangeGroup,
} from "../lib/changeset";
import type { Commit } from "../api/repository";
import {
  errorText,
  useAddCommitComment,
  useBranches,
  useCommit,
  useCommitComments,
  useCommits,
  useCommitTextDiff,
  useProject,
  useRoutineContent,
} from "../api/queries";
import { formatDate, timeAgo } from "../lib/time";
import { initials } from "../lib/initials";
import { shortSha } from "../lib/format";

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
            role={project?.your_role}
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
  role,
}: {
  commit: CommitDetail;
  projectName?: string;
  slug?: string;
  projectId?: number;
  role?: string;
}) {
  const [showNumbers, setShowNumbers] = useState(true);
  // The tab strip switches the main view: "changes" (default) draws every diff
  // the commit carries; "discussion" holds the comment thread; "files" shows
  // the whole-project tree with a routine viewer.
  const [tab, setTab] = useState<"discussion" | "changes" | "files">(
    "changes",
  );
  // Persistent discussion: the backend stores commit comments (flat, threaded
  // by parent_id at any depth); posting refreshes the list.
  const commentsQ = useCommitComments(projectId, commit.sha);
  const addComment = useAddCommitComment(projectId, commit.sha);
  const comments = commentsQ.data ?? [];

  // Files-tab selection lives here (not inside FilesBrowser) so it survives
  // switching to the Changes tab and back. Nothing is selected by default —
  // the stage prompts to pick a file — and the selection resets when the
  // commit changes.
  const [filesSel, setFilesSel] = useState<RoutineSelection | null>(null);
  const [filesEntity, setFilesEntity] = useState<TreeNode | null>(null);
  useEffect(() => {
    setFilesSel(null);
    setFilesEntity(null);
  }, [commit.sha]);

  // Revert starts from the branch tip (the backend re-checks this inside its
  // write lock — the gating here is reinforcement). On a protected branch it
  // is the manager-only rollback path, so hide it from plain members there.
  const branchCommits = useCommits(projectId, commit.branch).data ?? null;
  const isLatest = branchCommits
    ? shortSha(branchCommits[0]?.sha ?? "") === commit.sha
    : false;
  const branches = useBranches(projectId).data ?? null;
  const isProtected =
    branches?.find((b) => b.name === commit.branch)?.isProtected ?? false;
  const isManager = role === "owner" || role === "admin";
  const hasHistory = (branchCommits?.length ?? 0) > 1;
  const canRevert = isLatest && hasHistory && (!isProtected || isManager);
  const revertNote = !isLatest
    ? "Revert is only available on the branch's latest commit."
    : !hasHistory
      ? "There is no earlier commit to revert to."
      : isProtected && !isManager
        ? "Only owners and admins can revert a protected branch."
        : null;
  const [revertOpen, setRevertOpen] = useState(false);

  return (
    <div className="mr-page">
      <nav className="crumb">
        <Link to="/organization">Repositories</Link>
        <span className="crumb-sep">/</span>
        {projectName ? (
          <Link to={`/organization/${slug}`}>{projectName}</Link>
        ) : (
          <span>Repository</span>
        )}
        <span className="crumb-sep">/</span>
        <span>Commit</span>
      </nav>

      <CommitHeader commit={commit} />
      <MetaRow commit={commit} />

      <div className="repo-grid mr-grid">
        <div className="repo-col">
          <OverviewCard commit={commit} />
          <Tabs
            commentCount={comments.length}
            activeTab={tab}
            onSelect={setTab}
          />

          {tab === "discussion" ? (
            <Discussion
              comments={comments}
              loading={commentsQ.isPending}
              loadError={commentsQ.error}
              posting={addComment.isPending}
              postError={addComment.error}
              onAdd={(body, parentId) => addComment.mutate({ body, parentId })}
            />
          ) : tab === "changes" ? (
            <ChangesTab
              commit={commit}
              projectId={projectId}
              showNumbers={showNumbers}
              onToggleNumbers={() => setShowNumbers((v) => !v)}
            />
          ) : (
            <FilesBrowser
              tree={commit.tree}
              files={commit.files}
              fullContent={commit.fullContent}
              projectId={projectId}
              sha={commit.sha}
              l5xPath={commit.l5xPath}
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
        </div>

        <aside className="repo-rail cm-rail">
          <Dismissible id="about-commits">
            <AboutCommitsCard />
          </Dismissible>
          <FilesChangedCard files={commit.fileStats} />
          <ActionsCard
            slug={slug}
            branch={commit.branch}
            canRevert={canRevert}
            revertNote={revertNote}
            onRevert={() => setRevertOpen(true)}
          />
        </aside>
      </div>

      {revertOpen && branchCommits && slug && (
        <RevertModal
          slug={slug}
          branch={commit.branch}
          commits={branchCommits}
          onClose={() => setRevertOpen(false)}
        />
      )}
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
          Commit on{" "}
          <span className="branch-tag">
            <GitBranch size={12} strokeWidth={2} />
            {commit.branch}
          </span>{" "}
          by {commit.author}
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
        <span className="branch-tag">
          <GitBranch size={13} strokeWidth={2} />
          {commit.branch}
        </span>
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
const SUMMARY_PREVIEW = 6;

function OverviewCard({ commit }: { commit: CommitDetail }) {
  // Long summaries start truncated; "+N more changes" expands the full list
  // in a scrollable box.
  const [expanded, setExpanded] = useState(false);
  const hidden = commit.summary.length - SUMMARY_PREVIEW;
  const shown = expanded
    ? commit.summary
    : commit.summary.slice(0, SUMMARY_PREVIEW);

  return (
    <section className="cm-overview">
      <div className="cm-ov-block">
        <div className="cm-ov-label">Commit message</div>
        <p className="cm-ov-message">{commit.message}</p>
      </div>
      <div className="cm-ov-block cm-ov-summary">
        <div className="cm-ov-label">Commit summary</div>
        {commit.summary.length > 0 ? (
          <>
            <ul className={`cm-ov-list${expanded ? " expanded" : ""}`}>
              {shown.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
            {hidden > 0 && !expanded && (
              <button
                type="button"
                className="link-btn cm-ov-more"
                onClick={() => setExpanded(true)}
              >
                +{hidden} more changes
              </button>
            )}
          </>
        ) : (
          <p className="cm-ov-message muted">No summary provided.</p>
        )}
      </div>
    </section>
  );
}

// ---- Tabs ----
type CommitTab = "discussion" | "changes" | "files";

function Tabs({
  commentCount,
  activeTab,
  onSelect,
}: {
  commentCount: number;
  activeTab: CommitTab;
  onSelect: (t: CommitTab) => void;
}) {
  const tabs: { key: CommitTab; label: string; count?: number }[] = [
    { key: "changes", label: "Changes" },
    { key: "discussion", label: "Discussion", count: commentCount },
    { key: "files", label: "Files" },
  ];
  return (
    <TabStrip tabs={tabs} active={activeTab} onSelect={onSelect} className="cm-tabs" />
  );
}

// ---- Files tab: project tree + routine viewer ----
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
  l5xPath,
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
  l5xPath: string | null;
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
            selectedEntityKey={entity?.key ?? null}
            onSelectRoutine={onSelectRoutine}
            onSelectEntity={onSelectEntity}
            onClear={onClear}
          />
        </aside>
        <div className="commit-diff-stage">
          {entity && !selected ? (
            <EntityPanel
              node={entity}
              ctx={{ projectId, sha, l5xPath }}
            />
          ) : !selected ? (
            <div className="rcard-empty">
              Select a file on the left to view it.
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

// ---- Changes tab ----
// The commit's full diff, laid out like the merge-request page: every changed
// routine drawn as a diff (ladder rungs schematically, structured text side by
// side), then the non-routine semantic changes (controller properties, tags,
// modules, AOIs, tasks) as old → new tables, then text diffs for any non-L5X
// files the commit touched.
function ChangesTab({
  commit,
  projectId,
  showNumbers,
  onToggleNumbers,
}: {
  commit: CommitDetail;
  projectId?: number;
  showNumbers: boolean;
  onToggleNumbers: () => void;
}) {
  const [zoom, setZoom] = useState(100);
  const entityGroups = entityChangeGroups(commit.changeSet);
  const textFiles = commit.changedFiles.filter((f) => f.kind === "file");
  const routineFiles = commit.files.filter((f) => f.changes.length > 0);

  if (
    routineFiles.length === 0 &&
    entityGroups.length === 0 &&
    textFiles.length === 0
  ) {
    return (
      <section className="mr-section">
        <div className="mr-empty">
          No changes to show — this may be the project's first commit. The
          Files tab shows everything it contains.
        </div>
      </section>
    );
  }

  let section = 0;
  return (
    <>
      <div className="pr-changes-bar">
        <span className="pr-changes-title">
          Changed files
          <span className="mr-section-count">
            {commit.changedFiles.length || commit.filesChanged}
          </span>
        </span>
        <div className="mr-section-tools">
          <label className="mr-toggle">
            <input
              type="checkbox"
              checked={showNumbers}
              onChange={onToggleNumbers}
            />
            Show rung numbers
          </label>
          <ZoomControl zoom={zoom} onZoom={setZoom} />
        </div>
      </div>
      {routineFiles.map((f) => (
        <FileSection
          key={f.name}
          index={++section}
          file={f}
          showNumbers={showNumbers}
          zoom={zoom}
        />
      ))}
      {entityGroups.length > 0 && (
        <EntityChangesSection index={++section} groups={entityGroups} />
      )}
      {textFiles.map((f) => (
        <TextFileSection
          key={f.path}
          index={++section}
          file={f}
          projectId={projectId}
          sha={commit.sha}
        />
      ))}
    </>
  );
}

const KIND_BADGE: Record<EntityChange["kind"], string> = {
  added: "green",
  removed: "red",
  modified: "orange",
};

// Any JSON value as a short cell string.
function fmtVal(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

// The non-routine semantic changes as one numbered section, a titled table per
// entity kind (controller properties, tags, modules, …).
function EntityChangesSection({
  index,
  groups,
}: {
  index: number;
  groups: EntityChangeGroup[];
}) {
  const count = groups.reduce((n, g) => n + g.entities.length, 0);
  return (
    <section className="mr-section pr-file">
      <div className="mr-section-head">
        <div className="mr-section-title">
          <span className="mr-section-num">{index}.</span>
          Configuration &amp; tags
          <span className="mr-section-count">
            {count} {count === 1 ? "change" : "changes"}
          </span>
        </div>
      </div>
      <div className="pr-file-body">
        {groups.map((g) => (
          <div className="pr-routine" key={g.title}>
            <div className="pr-routine-head">
              <span className="pr-routine-name">{g.title}</span>
            </div>
            <EntityGroupTable entities={g.entities} />
          </div>
        ))}
      </div>
    </section>
  );
}

// One group's entities as a table: a row per changed field, with the entity's
// name and change badge spanning its field rows. An added or removed entity
// with no field detail still gets a row of its own.
function EntityGroupTable({ entities }: { entities: EntityChange[] }) {
  return (
    <div className="dtable-scroll">
      <table className="dtable l5x-table entity-diff">
        <thead>
          <tr>
            <th>Name</th>
            <th>Change</th>
            <th>Property</th>
            <th>Previous</th>
            <th>New</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((e) => {
            const rows = e.fields.length > 0 ? e.fields : [null];
            return rows.map((f, i) => (
              <tr key={`${e.name}-${f?.path ?? i}`}>
                {i === 0 && (
                  <>
                    <td className="cell-strong" rowSpan={rows.length}>
                      {e.name}
                    </td>
                    <td rowSpan={rows.length}>
                      <span className={`badge ${KIND_BADGE[e.kind]}`}>
                        {e.kind}
                      </span>
                    </td>
                  </>
                )}
                <td className="mono-cell">{f?.path ?? "—"}</td>
                <td className="mono-cell entity-old">
                  {f ? fmtVal(f.old) : "—"}
                </td>
                <td className="mono-cell entity-new">
                  {f ? fmtVal(f.new) : "—"}
                </td>
              </tr>
            ));
          })}
        </tbody>
      </table>
    </div>
  );
}

// One non-L5X file's text diff, fetched lazily when the tab renders. Binary
// files (and files with no text differences) fall back to a note.
function TextFileSection({
  index,
  file,
  projectId,
  sha,
}: {
  index: number;
  file: ChangedFile;
  projectId?: number;
  sha: string;
}) {
  const q = useCommitTextDiff(projectId, sha, file.path);
  const name = file.path.replace(/^files\//, "");
  return (
    <section className="mr-section pr-file">
      <div className="mr-section-head">
        <div className="mr-section-title">
          <span className="mr-section-num">{index}.</span>
          <span className="pr-file-ico">
            <FileCode2 size={15} strokeWidth={1.8} />
          </span>
          <span className="pr-file-name">{name}</span>
          <span className={`badge ${KIND_BADGE[file.change]}`}>
            {file.change}
          </span>
        </div>
      </div>
      <div className="pr-file-body">
        {q.isPending ? (
          <div className="rcard-empty">Loading diff…</div>
        ) : q.error ? (
          <div className="rcard-empty">
            {errorText(q.error, "Couldn't load this file's diff.")}
          </div>
        ) : !q.data ? (
          <div className="rcard-empty">No diff available.</div>
        ) : q.data.binary || q.data.unified == null ? (
          <div className="rcard-empty">Binary file — no text diff to show.</div>
        ) : q.data.unified.trim() === "" ? (
          <div className="rcard-empty">No text differences.</div>
        ) : (
          <UnifiedDiff unified={q.data.unified} />
        )}
      </div>
    </section>
  );
}

// A unified diff, one line per row, tinted by its +/- prefix; hunk and file
// headers render muted.
function UnifiedDiff({ unified }: { unified: string }) {
  const lines = unified.replace(/\n$/, "").split("\n");
  return (
    <div className="udiff">
      {lines.map((l, i) => {
        const cls =
          l.startsWith("+++") ||
          l.startsWith("---") ||
          l.startsWith("@@") ||
          l.startsWith("diff ") ||
          l.startsWith("index ")
            ? " ud-meta"
            : l.startsWith("+")
              ? " ud-add"
              : l.startsWith("-")
                ? " ud-rem"
                : "";
        return (
          <div className={`ud-line${cls}`} key={i}>
            {l || " "}
          </div>
        );
      })}
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

function ActionsCard({
  slug,
  branch,
  canRevert,
  revertNote,
  onRevert,
}: {
  slug?: string;
  branch?: string;
  canRevert: boolean;
  revertNote: string | null;
  onRevert: () => void;
}) {
  // Opening a merge request from this commit's branch is a real flow (the
  // create-merge-request page), so this links straight to it with the branch
  // pre-selected as the source. Revert opens the target-picking dialog; when
  // it isn't available here, the note under the button says why.
  const canCreate = Boolean(slug && branch);
  return (
    <section className="rail-section cm-actions">
      <div className="rail-head">
        <span className="rail-title">Actions</span>
      </div>
      {canCreate ? (
        <Link
          to={`/organization/${slug}/merge-requests/new?source=${encodeURIComponent(branch!)}`}
          className="btn btn-outline btn-block btn-sm"
        >
          <GitPullRequestArrow size={15} strokeWidth={1.9} />
          Create merge request
        </Link>
      ) : (
        <button className="btn btn-outline btn-block btn-sm" disabled>
          <GitPullRequestArrow size={15} strokeWidth={1.9} />
          Create merge request
        </button>
      )}
      <button
        className="btn btn-block btn-sm cm-revert"
        disabled={!canRevert}
        title={revertNote ?? undefined}
        onClick={onRevert}
      >
        <RotateCcw size={15} strokeWidth={1.9} />
        Revert commit
      </button>
      {revertNote && <p className="cm-revert-note">{revertNote}</p>}
    </section>
  );
}

// The revert dialog: explains what a revert does, and picks WHICH earlier
// commit to restore. Preview navigates to the revert page, which shows the
// exact changes (diff tip → target) and holds the Confirm button.
function RevertModal({
  slug,
  branch,
  commits,
  onClose,
}: {
  slug: string;
  branch: string;
  commits: Commit[];
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [target, setTarget] = useState<string | null>(null);
  const tip = commits[0];
  const options = commits.slice(1);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal-wide revert-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="modal-title">
          <TriangleAlert size={17} strokeWidth={2} className="revert-modal-ico" />
          Revert {branch}
        </h3>
        <p className="revert-modal-intro">
          Reverting restores an earlier state of{" "}
          <span className="branch-tag">
            <GitBranch size={12} strokeWidth={2} />
            {branch}
          </span>{" "}
          as <strong>one new commit</strong> on top of{" "}
          <span className="cm-commit-sha">{tip && shortSha(tip.sha)}</span>. Nothing
          is deleted — the commits in between stay in the history. Pick the
          commit whose state you want back, then preview exactly what will
          change before anything happens.
        </p>
        <div className="revert-commit-list" role="radiogroup">
          {options.map((c) => (
            <label
              key={c.sha}
              className={`revert-commit${target === c.sha ? " selected" : ""}`}
            >
              <input
                type="radio"
                name="revert-target"
                checked={target === c.sha}
                onChange={() => setTarget(c.sha)}
              />
              <span className="revert-commit-main">
                <span className="revert-commit-msg">{c.message}</span>
                <span className="revert-commit-meta">
                  <span className="mr-meta-mono">{shortSha(c.sha)}</span> ·{" "}
                  {c.author} · {timeAgo(c.at)}
                </span>
              </span>
            </label>
          ))}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!target || !tip}
            onClick={() =>
              navigate(
                `/organization/${slug}/revert?branch=${encodeURIComponent(branch)}` +
                  `&target=${target}&tip=${tip!.sha}`,
              )
            }
          >
            Preview changes
          </button>
        </div>
      </div>
    </div>
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
        to={slug ? `/organization/${slug}` : "/organization"}
        className="btn btn-primary btn-sm"
      >
        Back to repository
      </Link>
    </div>
  );
}
