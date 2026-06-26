import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
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
import { TopBar } from "../app/TopBar";
import { RoutineLadderDiffView } from "../components/LadderDiff";
import { ApiError } from "../api/client";
import {
  demoCommit,
  type CommitDetail,
  type CommitFileStat,
} from "../api/commit";
import type {
  MRCodeDiff,
  MRComment,
  PRFile,
  PRRoutineChange,
} from "../api/mergeRequest";
import { errorText, useCommit, useProject } from "../api/queries";
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
  // A status-0 (unreachable) project error isn't fatal: the commit query falls
  // back to demo data, so the page still renders.
  const projectFatal =
    projectError &&
    !(projectError instanceof ApiError && projectError.status === 0);
  const error = projectFatal
    ? errorText(projectError, "Failed to load commit.")
    : commitQuery.error && !notFound
      ? errorText(commitQuery.error, "Failed to load commit.")
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
        ) : !commit ? (
          <div className="page-pad">
            <EmptyCommit slug={slug} />
          </div>
        ) : (
          <CommitReviewView commit={commit} projectName={project?.name} slug={slug} />
        )}
      </div>
    </>
  );
}

// Presentational commit view, independent of data loading so it can also back
// the dev preview route below.
function CommitReviewView({
  commit,
  projectName,
  slug,
}: {
  commit: CommitDetail;
  projectName?: string;
  slug?: string;
}) {
  const [showNumbers, setShowNumbers] = useState(true);
  // Locally-added comments. There's no commit-comments backend endpoint yet, so
  // new comments live in component state and reset when the commit changes.
  const [added, setAdded] = useState<MRComment[]>([]);
  useEffect(() => setAdded([]), [commit.sha]);
  const comments = [...commit.comments, ...added];

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

      <div className="repo-grid mr-grid">
        <div className="repo-col">
          <OverviewCard commit={commit} />
          <Tabs commit={commit} />

          <ChangesToolbar
            count={commit.files.length}
            showNumbers={showNumbers}
            onToggle={() => setShowNumbers((v) => !v)}
          />
          {commit.files.map((file, i) => (
            <FileSection
              key={i}
              index={i + 1}
              file={file}
              showNumbers={showNumbers}
            />
          ))}

          <Discussion
            comments={comments}
            onAdd={(c) => setAdded((prev) => [...prev, c])}
          />
        </div>

        <aside className="repo-rail cm-rail">
          <CommitDetailsCard commit={commit} />
          <FilesChangedCard files={commit.fileStats} />
          <ActionsCard />
        </aside>
      </div>
    </div>
  );
}

// Dev-only preview: renders the page with self-contained demo data so the look
// can be checked without a backend or signing in. Wired in App.tsx under DEV.
export function CommitReviewPreview() {
  const commit = demoCommit("a7f3c9d");
  return (
    <>
      <TopBar />
      <div className="app-scroll">
        <CommitReviewView
          commit={commit}
          projectName="Packaging Line 3"
          slug="packaging-line-3"
        />
      </div>
    </>
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
function Tabs({ commit }: { commit: CommitDetail }) {
  const tabs: { key: string; label: string; count?: number }[] = [
    { key: "changes", label: "Changes" },
    { key: "files", label: "Files" },
    { key: "comments", label: "Comments", count: commit.comments.length },
    { key: "activity", label: "Activity" },
  ];
  return (
    <nav className="pr-tabs cm-tabs">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`pr-tab${t.key === "changes" ? " active" : ""}`}
          type="button"
        >
          {t.label}
          {t.count != null && <span className="pr-tab-count">{t.count}</span>}
        </button>
      ))}
    </nav>
  );
}

// ---- Changes, grouped by file ----
// Toolbar above the changed-file list: file count on the left, diff controls
// (rung numbers, zoom) on the right — they apply to every diff below.
function ChangesToolbar({
  count,
  showNumbers,
  onToggle,
}: {
  count: number;
  showNumbers: boolean;
  onToggle: () => void;
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
        <ZoomControl />
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
}: {
  index: number;
  file: PRFile;
  showNumbers: boolean;
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
      <div className="pr-file-body">
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

function ZoomControl() {
  const [zoom, setZoom] = useState(100);
  return (
    <div className="zoom cm-zoom">
      <span className="zoom-word">Zoom:</span>
      <button
        className="zoom-btn"
        type="button"
        aria-label="Zoom out"
        onClick={() => setZoom((z) => Math.max(50, z - 10))}
      >
        <Minus size={14} strokeWidth={2} />
      </button>
      <span className="zoom-val">{zoom}%</span>
      <button
        className="zoom-btn"
        type="button"
        aria-label="Zoom in"
        onClick={() => setZoom((z) => Math.min(200, z + 10))}
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
}: {
  comments: MRComment[];
  onAdd: (comment: MRComment) => void;
}) {
  return (
    <section className="mr-section">
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
                  <button className="disc-kebab" type="button" aria-label="More">
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
function CommitDetailsCard({ commit }: { commit: CommitDetail }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Commit details</span>
      </div>
      <dl className="md-rows">
        <MdRow label="Branch" value={commit.branch} />
        <MdRow label="Parent commit" value={commit.parentSha} mono link />
        <MdRow label="Commit hash" value={commit.sha} mono copy />
      </dl>
      <dl className="md-rows cm-md-divide">
        <MdRow label="Files changed" value={String(commit.filesChanged)} />
        <MdRow label="Comments" value={String(commit.commentCount)} />
      </dl>
    </section>
  );
}

function MdRow({
  label,
  value,
  mono,
  link,
  copy,
}: {
  label: string;
  value: string;
  mono?: boolean;
  link?: boolean;
  copy?: boolean;
}) {
  return (
    <div className="md-row">
      <dt className="md-label">{label}</dt>
      <dd className={`md-val${mono ? " mono" : ""}${link ? " cm-link" : ""}`}>
        {value}
        {copy && (
          <button
            className="cm-copy"
            type="button"
            aria-label="Copy"
            onClick={() => navigator.clipboard?.writeText(value)}
          >
            <Copy size={13} strokeWidth={1.9} />
          </button>
        )}
      </dd>
    </div>
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

function ActionsCard() {
  return (
    <section className="rail-section cm-actions">
      <div className="rail-head">
        <span className="rail-title">Actions</span>
      </div>
      <button className="btn btn-outline btn-block btn-sm">
        <GitPullRequestArrow size={15} strokeWidth={1.9} />
        Create change request
      </button>
      <button className="btn btn-block btn-sm cm-revert">
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
