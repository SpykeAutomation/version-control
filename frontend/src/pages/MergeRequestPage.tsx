import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Circle,
  Clock,
  Eye,
  FileCode2,
  GitBranch,
  GitCommitHorizontal,
  GitFork,
  GitMerge,
  GitPullRequestArrow,
  Maximize2,
  ShieldAlert,
  Users,
} from "lucide-react";
import { FileSection, ZoomControl } from "../components/ChangesView";
import { Discussion } from "../components/Discussion";
import { ApiError } from "../api/client";
import {
  MR_STATUS_META,
  REVIEW_STATE_META,
  type MergeRequest,
  type MRCommitRow,
  type MRReviewer,
  type PRFile,
} from "../api/mergeRequest";
import {
  errorText,
  useCreateComment,
  useMergePull,
  useMergeRequest,
  useProject,
} from "../api/queries";
import type { MergeOutcome } from "../api/mergeRequest";
import { formatDate, timeAgo } from "../lib/time";

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function MergeRequestPage() {
  const { slug, mrId } = useParams();
  const { project, isPending: projectPending, error: projectError } =
    useProject(slug);
  const mrQuery = useMergeRequest(slug, mrId);

  const mr = mrQuery.data ?? null;
  const loading = (projectPending && !mr) || mrQuery.isPending;
  // A 404 means the merge request doesn't exist — show the empty state rather
  // than an error banner.
  const notFound =
    mrQuery.error instanceof ApiError && mrQuery.error.status === 404;
  const projectFatal = Boolean(projectError);
  const error = projectFatal
    ? errorText(projectError, "Failed to load merge request.")
    : mrQuery.error && !notFound
      ? errorText(mrQuery.error, "Failed to load merge request.")
      : null;

  return (
      <div className="app-scroll">
        {error ? (
          <div className="page-pad">
            <div className="panel-msg error">{error}</div>
          </div>
        ) : loading ? (
          <div className="page-pad">
            <div className="panel-msg">Loading merge request…</div>
          </div>
        ) : !mr ? (
          <div className="page-pad">
            <EmptyMerge slug={slug} />
          </div>
        ) : (
          <MergeRequestView
            mr={mr}
            projectName={project?.name}
            projectId={project?.id}
            slug={slug}
            mrId={mrId}
          />
        )}
      </div>
  );
}

// The presentational merge-request view, independent of data loading.
function MergeRequestView({
  mr,
  projectName,
  projectId,
  slug,
  mrId,
}: {
  mr: MergeRequest;
  projectName?: string;
  projectId?: number;
  slug?: string;
  mrId?: string;
}) {
  const [showNumbers, setShowNumbers] = useState(true);
  const [zoom, setZoom] = useState(100);
  const [tab, setTab] = useState<MrTab>("changes");
  const merge = useMergePull(slug, mrId, projectId);
  // Threaded discussion: posting (or replying) refetches the merge request,
  // which carries the comment list.
  const comment = useCreateComment(slug, mrId);
  const merged = mr.status === "merged";
  const onMerge = () => merge.mutate();
  // The merge buttons stay inert without a project id and while a merge is in
  // flight or already done.
  const disabled = !projectId || merge.isPending || merged;
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
        <span>Merge request</span>
      </nav>

      <MergeHeader
        mr={mr}
        onMerge={onMerge}
        disabled={disabled}
        pending={merge.isPending}
        merged={merged}
      />
      <MetaRow mr={mr} />
      <SummaryCard mr={mr} />

      <div className="repo-grid mr-grid">
        <div className="repo-col">
          <Tabs mr={mr} tab={tab} onSelect={setTab} />
          {tab === "changes" ? (
            <>
              <ChangesToolbar
                count={mr.files.length}
                showNumbers={showNumbers}
                onToggle={() => setShowNumbers((v) => !v)}
                zoom={zoom}
                onZoom={setZoom}
              />
              {mr.files.map((file, i) => (
                <FileSection
                  key={i}
                  index={i + 1}
                  file={file}
                  showNumbers={showNumbers}
                  zoom={zoom}
                />
              ))}
            </>
          ) : tab === "commits" ? (
            <CommitsList commits={mr.commits} slug={slug} />
          ) : (
            <FilesOverview files={mr.files} onOpenChanges={() => setTab("changes")} />
          )}
          <Discussion
            comments={mr.comments}
            posting={comment.isPending}
            postError={comment.error}
            onAdd={(body, parentId) => comment.mutate({ body, parentId })}
          />
        </div>

        <aside className="repo-rail mr-rail">
          <AboutMergeRequestsCard />
          <ReviewersCard reviewers={mr.reviewers} />
          <MergeDetails mr={mr} />
          <MergeActions
            targetBranch={mr.targetBranch}
            onMerge={onMerge}
            disabled={disabled}
            pending={merge.isPending}
            merged={merged}
            outcome={merge.data}
            error={merge.error ? errorText(merge.error, "Couldn't merge.") : null}
          />
        </aside>
      </div>
    </div>
  );
}

// ---- Header ----
function MergeHeader({
  mr,
  onMerge,
  disabled,
  pending,
  merged,
}: {
  mr: MergeRequest;
  onMerge: () => void;
  disabled: boolean;
  pending: boolean;
  merged: boolean;
}) {
  const s = MR_STATUS_META[mr.status];
  return (
    <header className="mr-head">
      <span className="mr-glyph" aria-hidden="true">
        <GitFork size={24} strokeWidth={1.8} />
      </span>
      <div className="mr-head-main">
        <div className="mr-title-row">
          <span className="pr-id">{mr.id}</span>
          <h1 className="mr-title">{mr.title}</h1>
        </div>
        <p className="mr-sub">
          Merge {mr.sourceBranch} into {mr.targetBranch}
        </p>
      </div>
      <div className="mr-actions">
        <span className={`pr-status ${s.tone}`}>
          <Eye size={15} strokeWidth={2} />
          {s.label}
        </span>
        <button className="btn-quiet" disabled title="Coming soon">
          Request changes
        </button>
        <button
          className="btn btn-approve btn-sm"
          type="button"
          onClick={onMerge}
          disabled={disabled}
        >
          <GitMerge size={15} strokeWidth={2} />
          {merged ? "Merged" : pending ? "Merging…" : "Approve & merge"}
          <ChevronDown size={15} strokeWidth={2} />
        </button>
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

function MetaRow({ mr }: { mr: MergeRequest }) {
  const leadReviewers = mr.reviewers.slice(0, 2);
  const reviewerNames = leadReviewers.map((r) => r.name).join(", ");
  return (
    <div className="mr-meta">
      <MetaCard icon={<GitBranch size={14} strokeWidth={1.8} />} label="Source branch">
        <span className="mr-meta-mono">{mr.sourceBranch}</span>
        <span className="mr-meta-sub">
          {mr.sourceSha ? `${mr.sourceSha} · ` : ""}
          {mr.sourceCommits} commits
        </span>
      </MetaCard>
      <MetaCard icon={<GitBranch size={14} strokeWidth={1.8} />} label="Target branch">
        <span className="mr-meta-mono">{mr.targetBranch}</span>
        <span className="mr-meta-sub">
          {mr.targetSha ? `${mr.targetSha} · ` : ""}
          {mr.targetCommits} commits
        </span>
      </MetaCard>
      <MetaCard icon={<Users size={14} strokeWidth={1.8} />} label="Author">
        <span className="author">
          <span className="author-av">{initials(mr.author)}</span>
          {mr.author}
        </span>
        <span className="mr-meta-sub">{timeAgo(mr.authorAt)}</span>
      </MetaCard>
      <MetaCard icon={<Users size={14} strokeWidth={1.8} />} label="Reviewers">
        <span className="mr-rev-line">
          <span className="mr-avstack">
            {leadReviewers.map((r) => (
              <span className="mr-av" key={r.name} title={r.name}>
                {initials(r.name)}
              </span>
            ))}
          </span>
          <span className="mr-rev-names" title={reviewerNames}>
            {reviewerNames}
          </span>
        </span>
      </MetaCard>
      <MetaCard icon={<Clock size={14} strokeWidth={1.8} />} label="Updated">
        <span className="mr-meta-strong">{timeAgo(mr.updatedAt)}</span>
        <span className="mr-meta-sub">{formatDate(mr.updatedAt)}</span>
      </MetaCard>
    </div>
  );
}

// ---- Merge request summary ----
function SummaryCard({ mr }: { mr: MergeRequest }) {
  return (
    <section className="pr-summary">
      <h2 className="pr-summary-title">Merge request summary</h2>
      <div className="pr-summary-body">
        <div className="pr-summary-text">
          <p className="mr-summary-lede">
            {mr.summary || "No description was provided for this merge request."}
          </p>
          {mr.bullets.length > 0 && (
            <ul className="mr-summary-list">
              {mr.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
        </div>
        {mr.safetyReview && (
          <div className="pr-summary-stats">
            <Sstat
              icon={<ShieldAlert size={16} strokeWidth={1.9} />}
              value=""
              label="Safety review required"
              tone="orange"
            />
          </div>
        )}
      </div>
    </section>
  );
}

function Sstat({
  icon,
  value,
  label,
  tone,
}: {
  icon: React.ReactNode;
  value: string;
  label: string;
  tone?: "orange";
}) {
  return (
    <div className={`pr-sstat${tone ? ` ${tone}` : ""}`}>
      <span className="pr-sstat-top">
        <span className="pr-sstat-ico">{icon}</span>
        {value && <span className="pr-sstat-num">{value}</span>}
      </span>
      <span className="pr-sstat-label">{label}</span>
    </div>
  );
}

// ---- Tabs ----
type MrTab = "changes" | "commits" | "files";

function Tabs({
  mr,
  tab,
  onSelect,
}: {
  mr: MergeRequest;
  tab: MrTab;
  onSelect: (t: MrTab) => void;
}) {
  const tabs: { key: MrTab; label: string; count?: number }[] = [
    { key: "changes", label: "Changes" },
    { key: "commits", label: "Commits", count: mr.commits.length || mr.sourceCommits },
    { key: "files", label: "Files", count: mr.files.length },
  ];
  return (
    <nav className="pr-tabs">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`pr-tab${t.key === tab ? " active" : ""}`}
          type="button"
          onClick={() => onSelect(t.key)}
        >
          {t.label}
          {t.count != null && <span className="pr-tab-count">{t.count}</span>}
        </button>
      ))}
    </nav>
  );
}

// ---- Commits tab ----
// The commits on the source branch, newest first, grouped by calendar day. Each
// row links to that commit's review page.
function CommitsList({
  commits,
  slug,
}: {
  commits: MRCommitRow[];
  slug?: string;
}) {
  if (commits.length === 0) {
    return (
      <section className="mr-section">
        <div className="mr-empty">No commits on this branch yet.</div>
      </section>
    );
  }

  // Group consecutive commits by the day they were authored. Commits arrive
  // newest-first, so the groups come out newest-first too.
  const groups: { day: string; items: MRCommitRow[] }[] = [];
  for (const c of commits) {
    const day = new Date(c.at).toDateString();
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.items.push(c);
    else groups.push({ day, items: [c] });
  }

  return (
    <section className="mr-section mr-commits">
      {groups.map((g) => (
        <div className="mr-commits-day" key={g.day}>
          <div className="mr-commits-daylabel">
            <GitCommitHorizontal size={14} strokeWidth={1.9} />
            Commits on {formatDate(g.items[0].at)}
          </div>
          <ul className="mr-commits-rows">
            {g.items.map((c) => (
              <CommitRow key={c.sha} commit={c} slug={slug} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function CommitRow({ commit, slug }: { commit: MRCommitRow; slug?: string }) {
  const stat =
    commit.additions != null || commit.deletions != null ? (
      <span className="mr-commit-diffstat">
        {commit.additions != null && (
          <span className="dadd">+{commit.additions}</span>
        )}
        {commit.deletions != null && (
          <span className="ddel">−{commit.deletions}</span>
        )}
      </span>
    ) : null;

  const inner = (
    <>
      <span className="mr-commit-main">
        <span className="mr-commit-msg">{commit.message}</span>
        <span className="mr-commit-meta">
          <span className="author">
            <span className="author-av">{initials(commit.author)}</span>
            {commit.author}
          </span>
          <span className="mr-commit-dot">·</span>
          <span className="mr-commit-time">{timeAgo(commit.at)}</span>
        </span>
      </span>
      <span className="mr-commit-right">
        {stat}
        <span className="mr-commit-sha">{commit.hash}</span>
      </span>
    </>
  );

  return (
    <li>
      {slug ? (
        <Link className="mr-commit-row" to={`/organization/${slug}/commit/${commit.sha}`}>
          {inner}
        </Link>
      ) : (
        <div className="mr-commit-row">{inner}</div>
      )}
    </li>
  );
}

// ---- Files tab ----
// A compact list of the changed files — names and per-file change counts — for a
// quick "what's touched" overview. Selecting a file jumps to its full diff in
// the Changes view.
function FilesOverview({
  files,
  onOpenChanges,
}: {
  files: PRFile[];
  onOpenChanges: () => void;
}) {
  if (files.length === 0) {
    return (
      <section className="mr-section">
        <div className="mr-empty">No files changed.</div>
      </section>
    );
  }
  return (
    <section className="mr-section mr-files">
      <ul className="mr-files-rows">
        {files.map((f) => {
          const bits: string[] = [];
          bits.push(
            `${f.changes.length} ${f.changes.length === 1 ? "routine" : "routines"}`,
          );
          if (f.rungsChanged)
            bits.push(
              `${f.rungsChanged} ${f.rungsChanged === 1 ? "rung" : "rungs"}`,
            );
          if (f.linesChanged)
            bits.push(
              `${f.linesChanged} ${f.linesChanged === 1 ? "line" : "lines"}`,
            );
          return (
            <li key={f.name}>
              <button
                type="button"
                className="mr-file-row"
                onClick={onOpenChanges}
              >
                <span className="pr-file-ico">
                  <FileCode2 size={15} strokeWidth={1.8} />
                </span>
                <span className="mr-file-name">{f.name}</span>
                <span className="mr-file-stat">{bits.join(" · ")}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ---- Changes, grouped by file ----
// Toolbar above the changed-file list: file count on the left, diff controls
// (rung numbers, zoom, fullscreen) on the right — they apply to every diff.
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
        <button className="mr-fs" type="button" aria-label="Fullscreen">
          <Maximize2 size={15} strokeWidth={1.9} />
        </button>
      </div>
    </div>
  );
}

// ---- Right rail ----
function reviewerStateIcon(tone: string): React.ReactNode {
  if (tone === "green") return <CheckCircle2 size={15} strokeWidth={2} />;
  if (tone === "orange") return <Clock size={14} strokeWidth={2} />;
  if (tone === "red") return <AlertTriangle size={14} strokeWidth={2} />;
  return <Circle size={13} strokeWidth={2} />;
}

function ReviewersCard({ reviewers }: { reviewers: MRReviewer[] }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Reviewers</span>
        <button className="link-btn" disabled title="Coming soon">Edit</button>
      </div>
      {reviewers.length === 0 && (
        <div className="rail-empty">No reviewers assigned.</div>
      )}
      <div className="rv-list">
        {reviewers.map((r) => {
          const m = REVIEW_STATE_META[r.state];
          return (
            <div className="rv-item" key={r.name}>
              <span className="author-av">{initials(r.name)}</span>
              <div className="rv-meta">
                <div className="rv-name">{r.name}</div>
                <div className="rv-role">{r.role}</div>
              </div>
              <span className={`mr-state ${m.tone}`}>
                {reviewerStateIcon(m.tone)}
                {m.label}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function MergeDetails({ mr }: { mr: MergeRequest }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Merge request details</span>
      </div>
      <dl className="md-rows">
        <MdRow label="Source branch" value={mr.sourceBranch} />
        <MdRow label="Target branch" value={mr.targetBranch} />
        <MdRow label="Commits" value={String(mr.sourceCommits)} />
        <MdRow label="Files changed" value={String(mr.files.length)} />
      </dl>
      <div className="md-changed-head">Changed items</div>
      <div className="md-changed">
        {mr.files.map((f) => (
          <div className="md-changed-row" key={f.name}>
            <FileCode2 size={14} strokeWidth={1.8} />
            <span className="md-changed-name">{f.name}</span>
            <span className="md-changed-val">
              {f.changes.length} {f.changes.length === 1 ? "routine" : "routines"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function MdRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="md-row">
      <dt className="md-label">{label}</dt>
      <dd className={`md-val${mono ? " mono" : ""}`}>{value}</dd>
    </div>
  );
}

function MergeActions({
  targetBranch,
  onMerge,
  disabled,
  pending,
  merged,
  outcome,
  error,
}: {
  targetBranch: string;
  onMerge: () => void;
  disabled: boolean;
  pending: boolean;
  merged: boolean;
  outcome?: MergeOutcome;
  error?: string | null;
}) {
  return (
    <section className="rail-section mr-merge-card">
      <div className="mr-merge-title">Ready to merge</div>
      <p className="mr-merge-note">
        Once merged, the changes in this branch will be reflected on{" "}
        <span className="mr-branch">{targetBranch}</span>.
      </p>
      {outcome?.status === "conflict" && (
        <div className="panel-msg error">{outcome.message}</div>
      )}
      {error && <div className="panel-msg error">{error}</div>}
      <button
        className="btn btn-approve btn-block"
        type="button"
        onClick={onMerge}
        disabled={disabled}
      >
        <GitMerge size={16} strokeWidth={2} />
        {merged ? "Merged" : pending ? "Merging…" : "Approve & merge"}
        <ChevronDown size={15} strokeWidth={2} />
      </button>
      <button className="btn btn-text btn-block" disabled title="Coming soon">
        <GitPullRequestArrow size={16} strokeWidth={1.9} />
        Request changes
      </button>
    </section>
  );
}

function AboutMergeRequestsCard() {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">About merge requests</span>
      </div>
      <div className="about-body">
        <p className="about-intro">
          A merge request proposes bringing one branch's changes into another,
          with review before they land.
        </p>
        <div className="about-item">
          <span className="about-ico">
            <GitPullRequestArrow size={16} strokeWidth={1.9} />
          </span>
          <div>
            <div className="about-item-title">Review</div>
            <div className="about-item-desc">
              Reviewers compare the changes and discuss them, then approve or
              request changes before anything merges.
            </div>
          </div>
        </div>
        <div className="about-item">
          <span className="about-ico">
            <GitMerge size={16} strokeWidth={1.9} />
          </span>
          <div>
            <div className="about-item-title">Merging</div>
            <div className="about-item-desc">
              Once approved and merged, the source branch's changes become part
              of the target branch.
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

function EmptyMerge({ slug }: { slug?: string }) {
  return (
    <div className="empty-state">
      <span className="empty-ico">
        <GitPullRequestArrow size={24} strokeWidth={1.6} />
      </span>
      <h3>Merge request not found</h3>
      <p>We couldn't find that merge request. It may have been merged or closed.</p>
      <Link to={slug ? `/organization/${slug}` : "/organization"} className="btn btn-primary btn-sm">
        Back to repository
      </Link>
    </div>
  );
}
