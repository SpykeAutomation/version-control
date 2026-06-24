import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  Clock,
  FileCode2,
  GitBranch,
  GitMerge,
  GitPullRequestArrow,
  MessageSquare,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { RungView } from "../components/Ladder";
import { listProjects, type ProjectRow } from "../api/projects";
import { ApiError } from "../api/client";
import {
  CHECK_STATE_META,
  getMergeRequest,
  MR_STATUS_META,
  REVIEW_STATE_META,
  type MergeRequest,
  type MRCheck,
  type MRCodeDiff,
  type MRComment,
  type MRLadderDiff,
  type MRLadderSide,
  type MRReviewer,
} from "../api/mergeRequest";
import { formatDate, timeAgo } from "../lib/time";

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

function hasRungs(d: MRLadderDiff): boolean {
  return d.left.rungs.length > 0 || d.right.rungs.length > 0;
}
function hasCode(d: MRCodeDiff): boolean {
  return d.left.lines.length > 0 || d.right.lines.length > 0;
}

export function MergeRequestPage() {
  const { slug, mrId } = useParams();
  const [projects, setProjects] = useState<ProjectRow[] | null>(null);
  const [mr, setMr] = useState<MergeRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNumbers, setShowNumbers] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([listProjects(), getMergeRequest(slug ?? "", mrId ?? "")])
      .then(([ps, m]) => {
        if (!active) return;
        setProjects(ps);
        setMr(m);
      })
      .catch((e) => {
        if (!active) return;
        if (e instanceof ApiError && e.status === 404) setMr(null);
        else
          setError(
            e instanceof ApiError ? e.message : "Failed to load merge request.",
          );
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [slug, mrId]);

  const project = useMemo(
    () => projects?.find((p) => p.slug === slug) ?? null,
    [projects, slug],
  );

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
            <div className="panel-msg">Loading merge request…</div>
          </div>
        ) : !mr ? (
          <div className="page-pad">
            <EmptyMerge slug={slug} />
          </div>
        ) : (
          <div className="mr-page">
            <nav className="crumb">
              <Link to="/projects">Projects</Link>
              <span className="crumb-sep">/</span>
              {project ? (
                <Link to={`/projects/${slug}`}>{project.name}</Link>
              ) : (
                <span>Project</span>
              )}
              <span className="crumb-sep">/</span>
              <span>Merge request</span>
            </nav>

            <MergeHeader mr={mr} slug={slug} />
            <MetaRow mr={mr} />

            <div className="repo-grid mr-grid">
              <div className="repo-col">
                <SummaryCard mr={mr} />
                {hasRungs(mr.ladder) && (
                  <LadderSection
                    diff={mr.ladder}
                    showNumbers={showNumbers}
                    onToggle={() => setShowNumbers((v) => !v)}
                  />
                )}
                {hasCode(mr.code) && <CodeSection diff={mr.code} />}
                <Discussion comments={mr.comments} count={mr.commentCount} />
              </div>

              <aside className="repo-rail mr-rail">
                <ChecksBanner checks={mr.checks} />
                <ReviewersCard reviewers={mr.reviewers} />
                <ChecksCard checks={mr.checks} />
                <ImpactedTags tags={mr.impactedTags} />
                <MergeDetails mr={mr} />
                <MergeActions mr={mr} />
              </aside>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// ---- Header ----
function MergeHeader({ mr, slug }: { mr: MergeRequest; slug?: string }) {
  const s = MR_STATUS_META[mr.status];
  return (
    <header className="mr-head">
      <Link
        to={slug ? `/projects/${slug}` : "/projects"}
        className="mr-back"
        aria-label="Back to project"
      >
        <ArrowLeft size={18} strokeWidth={2} />
      </Link>
      <div className="mr-head-main">
        <div className="mr-title-row">
          <span className="mr-id">{mr.id}</span>
          <h1 className="mr-title">{mr.title}</h1>
        </div>
        <p className="mr-sub">
          Merge <span className="mr-branch">{mr.sourceBranch}</span> into{" "}
          <span className="mr-branch">{mr.targetBranch}</span>
        </p>
      </div>
      <div className="mr-actions">
        <span className={`badge ${s.tone}`}>
          <span className="badge-dot" />
          {s.label}
        </span>
        <button className="btn btn-outline btn-sm">Request changes</button>
        <button className="btn btn-approve btn-sm">
          <GitMerge size={15} strokeWidth={2} />
          Approve &amp; merge
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
  return (
    <div className="mr-meta">
      <MetaCard icon={<GitBranch size={14} strokeWidth={1.8} />} label="Source branch">
        <span className="mr-meta-mono">{mr.sourceBranch}</span>
        <span className="mr-meta-sub">{mr.sourceCommits} commits</span>
      </MetaCard>
      <MetaCard icon={<GitBranch size={14} strokeWidth={1.8} />} label="Target branch">
        <span className="mr-meta-mono">{mr.targetBranch}</span>
        <span className="mr-meta-sub">{mr.targetCommits} commits</span>
      </MetaCard>
      <MetaCard icon={<GitPullRequestArrow size={14} strokeWidth={1.8} />} label="Author">
        <span className="author">
          <span className="author-av">{initials(mr.author)}</span>
          {mr.author}
        </span>
        <span className="mr-meta-sub">{timeAgo(mr.authorAt)}</span>
      </MetaCard>
      <MetaCard icon={<Users size={14} strokeWidth={1.8} />} label="Reviewers">
        <span className="mr-avstack">
          {mr.reviewers.map((r) => (
            <span className="mr-av" key={r.name} title={r.name}>
              {initials(r.name)}
            </span>
          ))}
        </span>
        <span className="mr-meta-sub">{mr.reviewers.length} assigned</span>
      </MetaCard>
      <MetaCard icon={<Clock size={14} strokeWidth={1.8} />} label="Updated">
        <span className="mr-meta-strong">{timeAgo(mr.updatedAt)}</span>
        <span className="mr-meta-sub">{formatDate(mr.updatedAt)}</span>
      </MetaCard>
      <MetaCard icon={<CheckCircle2 size={14} strokeWidth={1.8} />} label="Checks">
        <span className="mr-meta-strong">{checkSummary(mr.checks)}</span>
        <span className="mr-meta-sub">
          {mr.checks.length} check{mr.checks.length === 1 ? "" : "s"}
        </span>
      </MetaCard>
    </div>
  );
}

function checkSummary(checks: MRCheck[]): string {
  const passed = checks.filter((c) => c.state === "passed").length;
  const warn = checks.filter((c) => c.state === "warning" || c.state === "pending").length;
  const failed = checks.filter((c) => c.state === "failed").length;
  const parts: string[] = [];
  if (passed) parts.push(`${passed} passed`);
  if (warn) parts.push(`${warn} pending`);
  if (failed) parts.push(`${failed} failed`);
  return parts.join(", ") || "No checks";
}

// ---- Merge summary ----
function SummaryCard({ mr }: { mr: MergeRequest }) {
  return (
    <section className="rcard mr-summary">
      <div className="rcard-head">
        <span className="rcard-title">Merge summary</span>
      </div>
      <div className="mr-summary-body">
        <div className="mr-summary-text">
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
        <div className="mr-summary-stats">
          <Sstat
            icon={<GitMerge size={16} strokeWidth={1.8} />}
            value={String(mr.rungsChanged)}
            label="Rungs changed"
          />
          <Sstat
            icon={<FileCode2 size={16} strokeWidth={1.8} />}
            value={String(mr.routinesModified)}
            label="ST routine modified"
          />
          <Sstat
            icon={<MessageSquare size={16} strokeWidth={1.8} />}
            value={String(mr.commentCount)}
            label="Comments"
          />
          {mr.safetyReview && (
            <Sstat
              icon={<ShieldAlert size={16} strokeWidth={1.8} />}
              value="!"
              label="Safety review required"
              tone="orange"
            />
          )}
        </div>
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
    <div className={`mr-sstat${tone ? ` ${tone}` : ""}`}>
      <span className="mr-sstat-ico">{icon}</span>
      <span className="mr-sstat-num">{value}</span>
      <span className="mr-sstat-label">{label}</span>
    </div>
  );
}

// ---- Ladder logic changes ----
function LadderSection({
  diff,
  showNumbers,
  onToggle,
}: {
  diff: MRLadderDiff;
  showNumbers: boolean;
  onToggle: () => void;
}) {
  return (
    <section className="mr-section">
      <div className="mr-section-head">
        <div className="mr-section-title">
          Ladder logic changes
          <span className="mr-section-count">{diff.networks} networks</span>
        </div>
        <label className="mr-toggle">
          <input type="checkbox" checked={showNumbers} onChange={onToggle} />
          Show rung numbers
        </label>
      </div>
      <div className="diff-panels">
        <LadderPanel side="left" side_data={diff.left} showNumbers={showNumbers} />
        <LadderPanel side="right" side_data={diff.right} showNumbers={showNumbers} />
      </div>
    </section>
  );
}

function LadderPanel({
  side,
  side_data,
  showNumbers,
}: {
  side: "left" | "right";
  side_data: MRLadderSide;
  showNumbers: boolean;
}) {
  return (
    <section className={`diff-panel diff-${side}`}>
      <header className="diff-panel-head">
        <span className="dph-ref">{side_data.ref}</span>
        <span className={`dph-ver ${side === "right" ? "green" : "gray"}`}>
          {side_data.version}
        </span>
      </header>
      <div className="diff-panel-body">
        {side_data.rungs.map((r) => (
          <RungView key={r.number} rung={r} showNumbers={showNumbers} showHighlight />
        ))}
      </div>
    </section>
  );
}

// ---- Structured text changes ----
function CodeSection({ diff }: { diff: MRCodeDiff }) {
  return (
    <section className="mr-section">
      <div className="mr-section-head">
        <div className="mr-section-title">
          Structured text changes
          <span className="mr-section-count">{diff.routine}</span>
        </div>
      </div>
      <div className="diff-panels">
        <CodePanel side="left" side_data={diff.left} />
        <CodePanel side="right" side_data={diff.right} />
      </div>
    </section>
  );
}

function CodePanel({
  side,
  side_data,
}: {
  side: "left" | "right";
  side_data: MRCodeDiff["left"];
}) {
  return (
    <section className={`diff-panel diff-${side}`}>
      <header className="diff-panel-head">
        <span className="dph-ref">{side_data.ref}</span>
        <span className={`dph-ver ${side === "right" ? "green" : "gray"}`}>
          {side_data.version}
        </span>
      </header>
      <div className="code-diff">
        {side_data.lines.map((l) => (
          <div className={`code-line cl-${l.kind}`} key={l.ln}>
            <span className="cl-num">{l.ln}</span>
            <span className="cl-sign">
              {l.kind === "added" ? "+" : l.kind === "removed" ? "−" : ""}
            </span>
            <span className="cl-text">{l.text || " "}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---- Discussion ----
function Discussion({ comments, count }: { comments: MRComment[]; count: number }) {
  return (
    <section className="mr-section">
      <div className="mr-section-head">
        <div className="mr-section-title">
          Discussion
          <span className="mr-section-count">{count}</span>
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
              <div className="disc-top">
                <span className="disc-who">{c.author}</span>
                <span className={`disc-role${c.isAuthor ? " author" : ""}`}>{c.role}</span>
                {c.on && <span className="disc-on">Commented on {c.on}</span>}
                <span className="disc-time">{timeAgo(c.at)}</span>
              </div>
              <p className="disc-body">{c.body}</p>
            </div>
          </article>
        ))}
        <div className="disc-reply">
          <button className="btn btn-outline btn-sm">Add comment</button>
        </div>
      </div>
    </section>
  );
}

// ---- Right rail ----
function ChecksBanner({ checks }: { checks: MRCheck[] }) {
  const failed = checks.some((c) => c.state === "failed");
  const warn = checks.some((c) => c.state === "warning" || c.state === "pending");
  const tone = failed ? "red" : warn ? "orange" : "green";
  return (
    <section className={`rail-section mr-checkbanner ${tone}`}>
      <span className="mr-checkbanner-ico">
        {failed ? (
          <ShieldAlert size={18} strokeWidth={1.9} />
        ) : warn ? (
          <ShieldAlert size={18} strokeWidth={1.9} />
        ) : (
          <ShieldCheck size={18} strokeWidth={1.9} />
        )}
      </span>
      <div className="mr-checkbanner-main">
        <div className="mr-checkbanner-text">{checkSummary(checks)}</div>
        <button className="link-btn">View details</button>
      </div>
    </section>
  );
}

function ReviewersCard({ reviewers }: { reviewers: MRReviewer[] }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Reviewers</span>
        <button className="link-btn">Edit</button>
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
                <span className="mr-state-dot" />
                {m.label}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ChecksCard({ checks }: { checks: MRCheck[] }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Checks</span>
        <button className="link-btn">View details</button>
      </div>
      {checks.length === 0 && <div className="rail-empty">No checks configured.</div>}
      <div className="chk-list">
        {checks.map((c) => {
          const m = CHECK_STATE_META[c.state];
          return (
            <div className="chk-item" key={c.label}>
              <span className={`chk-ico ${m.tone}`}>
                {c.state === "passed" ? (
                  <CheckCircle2 size={15} strokeWidth={2} />
                ) : (
                  <Clock size={14} strokeWidth={2} />
                )}
              </span>
              <span className="chk-label">{c.label}</span>
              <span className={`chk-state ${m.tone}`}>{m.label}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ImpactedTags({ tags }: { tags: string[] }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Impacted tags ({tags.length})</span>
        {tags.length > 0 && <button className="link-btn">View all</button>}
      </div>
      {tags.length === 0 ? (
        <div className="rail-empty">No tags impacted.</div>
      ) : (
        <div className="sym-chips">
          {tags.map((t) => (
            <span className="sym-chip" key={t}>
              {t}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function MergeDetails({ mr }: { mr: MergeRequest }) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Merge details</span>
      </div>
      <dl className="md-rows">
        <MdRow label="Source branch" value={mr.sourceBranch} mono />
        <MdRow label="Target branch" value={mr.targetBranch} mono />
        <MdRow label="Commits" value={String(mr.sourceCommits)} />
      </dl>
      <div className="md-changed-head">Changed items</div>
      <div className="md-changed">
        <div className="md-changed-row">
          <GitBranch size={14} strokeWidth={1.8} />
          <span className="md-changed-name">Ladder logic</span>
          <span className="md-changed-val">
            {mr.ladder.networks} networks · {mr.rungsChanged} rungs
          </span>
        </div>
        <div className="md-changed-row">
          <FileCode2 size={14} strokeWidth={1.8} />
          <span className="md-changed-name">Structured text</span>
          <span className="md-changed-val">{mr.routinesModified} routine</span>
        </div>
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

function MergeActions({ mr }: { mr: MergeRequest }) {
  const ready = mr.checks.every((c) => c.state === "passed");
  return (
    <section className="rail-section mr-merge-card">
      <div className="mr-merge-title">{ready ? "Ready to merge" : "Not ready to merge"}</div>
      <p className="mr-merge-note">All required checks must pass before merging.</p>
      <button className="btn btn-approve btn-block">
        <GitMerge size={16} strokeWidth={2} />
        Approve &amp; merge
        <ChevronDown size={15} strokeWidth={2} />
      </button>
      <button className="btn btn-outline btn-block">Request changes</button>
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
      <Link to={slug ? `/projects/${slug}` : "/projects"} className="btn btn-primary btn-sm">
        Back to project
      </Link>
    </div>
  );
}
