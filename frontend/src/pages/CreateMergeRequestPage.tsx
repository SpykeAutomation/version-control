// The "Create merge request" page: a form to open a request from a source
// branch into a target branch, with a live preview of the changes between them.
//
// The dynamic parts — the branch tips, the changes summary, the changed-file
// tree and the commit list — are all driven by real backend data via the same
// hooks the merge-request review page uses. Sections without a backend (labels,
// linked work items, checks) render their structure plus an empty state only,
// and never invent sample content.
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowRight,
  Bold,
  ChevronDown,
  Code2,
  Eye,
  FileCode2,
  FolderClosed,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  Italic,
  Link2,
  List,
  ListOrdered,
  Pencil,
  Plus,
  Table,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  queryKeys,
  useBranches,
  useChangeRequests,
  useCommits,
  useDiff,
  useMembers,
  useProject,
} from "../api/queries";
import { addReviewer, createChangeRequest } from "../api/mergeRequest";
import { ApiError } from "../api/client";
import { deriveChangeView } from "../lib/changeset";
import type { BranchSummary } from "../api/commits";
import type { Commit } from "../api/repository";
import { useAuth } from "../auth/AuthContext";
import { timeAgo } from "../lib/time";

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

const TITLE_LIMIT = 100;

export function CreateMergeRequestPage() {
  const { slug } = useParams();
  const [params] = useSearchParams();
  const { project, isPending: projectPending } = useProject(slug);
  const { data: branches } = useBranches(project?.id);

  // Resolve the default source and target once the branch list arrives. The
  // target defaults to the project's default branch ("main"); the source comes
  // from the ?source= query param when present, otherwise the most recently
  // active non-default branch — the one most likely to have unmerged changes to
  // preview, so the page lands on a meaningful comparison rather than a branch
  // that's already been merged. Both stay empty until branches load so the
  // selects start un-chosen rather than guessing.
  const defaults = useMemo(() => {
    if (!branches || branches.length === 0) return { source: "", target: "" };
    const def = branches.find((b) => b.isDefault) ?? branches[0];
    const requested = params.get("source") ?? undefined;
    const fromParam = requested
      ? branches.find((b) => b.name === requested)
      : undefined;
    // Newest-first by last commit date (ISO strings sort chronologically).
    const newestNonDefault = branches
      .filter((b) => b.name !== def.name)
      .sort((a, b) => (b.lastCommitAt ?? "").localeCompare(a.lastCommitAt ?? ""))[0];
    const source = fromParam ?? newestNonDefault ?? def;
    return { source: source.name, target: def.name };
  }, [branches, params]);

  return (
      <div className="app-scroll">
        {projectPending && !project ? (
          <div className="page-pad">
            <div className="panel-msg">Loading…</div>
          </div>
        ) : (
          <CreateMergeRequestView
            slug={slug}
            projectName={project?.name}
            projectId={project?.id}
            branches={branches ?? []}
            defaultSource={defaults.source}
            defaultTarget={defaults.target}
            initialTitle={params.get("title")}
            initialDescription={params.get("description")}
          />
        )}
      </div>
  );
}

type CreateTab = "overview" | "commits";

function CreateMergeRequestView({
  slug,
  projectName,
  projectId,
  branches,
  defaultSource,
  defaultTarget,
  initialTitle,
  initialDescription,
}: {
  slug?: string;
  projectName?: string;
  projectId?: number;
  branches: BranchSummary[];
  defaultSource: string;
  defaultTarget: string;
  initialTitle: string | null;
  initialDescription: string | null;
}) {
  const { user } = useAuth();
  const [tab, setTab] = useState<CreateTab>("overview");

  // The chosen target branch. It follows the resolved default until the user
  // picks their own (tracked by a "touched" flag so a late branch load doesn't
  // stomp a manual choice). The source is fixed: a merge request proposes the
  // branch you came from, so only the target is changeable.
  const [pickedTarget, setPickedTarget] = useState<string | null>(null);
  const sourceBranch = defaultSource;
  const targetBranch = pickedTarget ?? defaultTarget;
  const [editingBranches, setEditingBranches] = useState(false);

  const sourceInfo = branches.find((b) => b.name === sourceBranch);
  const targetInfo = branches.find((b) => b.name === targetBranch);

  // Only diff/compare when the two refs differ — comparing a branch with itself
  // yields nothing, so we skip the request and show the zero state instead.
  const comparable = Boolean(
    sourceBranch && targetBranch && sourceBranch !== targetBranch,
  );
  const diffBase = comparable ? targetBranch : undefined;
  const diffHead = comparable ? sourceBranch : undefined;

  const { data: changeSet } = useDiff(projectId, diffBase, diffHead);
  const view = useMemo(
    () => (comparable && changeSet ? deriveChangeView(changeSet) : null),
    [comparable, changeSet],
  );

  // Commits this request would merge: those on the source branch not already on
  // the target. Same client-side comparison the review page uses.
  const { data: srcCommits } = useCommits(projectId, comparable ? sourceBranch : "");
  const { data: tgtCommits } = useCommits(projectId, comparable ? targetBranch : "");
  const uniqueCommits = useMemo<Commit[]>(() => {
    if (!comparable || !srcCommits || !tgtCommits) return [];
    const seen = new Set(tgtCommits.map((c) => c.sha));
    return srcCommits.filter((c) => !seen.has(c.sha));
  }, [comparable, srcCommits, tgtCommits]);

  // An open request already covering this source → target pair makes a new
  // one a duplicate: creation is blocked and the existing request is linked.
  const { data: existingRequests } = useChangeRequests(projectId);
  const duplicate = useMemo(
    () =>
      comparable
        ? (existingRequests?.find(
            (c) =>
              c.open &&
              c.sourceBranch === sourceBranch &&
              c.targetBranch === targetBranch,
          ) ?? null)
        : null,
    [comparable, existingRequests, sourceBranch, targetBranch],
  );

  // Reviewers come from the project's members (real backend). The author is
  // excluded — you don't review your own request.
  const { data: members } = useMembers(projectId);
  const reviewerOptions = useMemo(
    () => members?.filter((m) => m.id !== user?.id) ?? [],
    [members, user?.id],
  );

  // The title prefills from the ?title= param (the upload flow passes the
  // commit message through), falling back to the source branch name — but only
  // until the user edits it (tracked by a "touched" flag so a late branch load
  // or a branch switch doesn't stomp a manual edit). The description prefills
  // from ?description= the same way.
  const suggestedTitle = (initialTitle ?? sourceBranch ?? "").slice(0, TITLE_LIMIT);
  const [titleTouched, setTitleTouched] = useState(false);
  const [titleInput, setTitleInput] = useState("");
  const title = titleTouched ? titleInput : suggestedTitle;
  const [description, setDescription] = useState(initialDescription ?? "");

  // Rung additions / removals across every changed routine, from the same ladder
  // summary the review page reads. These are real diff counts (rungs added /
  // removed), not added/removed whole entities — so a modified routine still
  // contributes the rungs it changed.
  const totals = useMemo(() => {
    if (!view) return { additions: 0, removals: 0 };
    return {
      additions: view.summary.rungsAdded,
      removals: view.summary.rungsRemoved,
    };
  }, [view]);

  const filesCount = view?.files.length ?? 0;
  const commitsCount = uniqueCommits.length;

  const counts = {
    commits: commitsCount,
  };

  // Opening the request: create the pull, then attach the chosen reviewers
  // (best-effort — a failed invite doesn't undo the request), then land on the
  // new request's page. Mirrors the create flow on the commit page.
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const canSubmit = Boolean(projectId && comparable && title.trim() && !duplicate);

  async function handleCreate(reviewerIds: number[]) {
    if (!projectId || !canSubmit || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const pr = await createChangeRequest(projectId, {
        title: title.trim(),
        description: description.trim(),
        sourceBranch,
        targetBranch,
      });
      const emails = reviewerIds
        .map((id) => members?.find((m) => m.id === id)?.email)
        .filter((e): e is string => Boolean(e));
      for (const email of emails) {
        try {
          await addReviewer(projectId, pr.number, email);
        } catch {
          // A failed reviewer invite shouldn't block opening the request.
        }
      }
      qc.invalidateQueries({ queryKey: ["projects", projectId] });
      qc.invalidateQueries({ queryKey: queryKeys.projects });
      navigate(`/organization/${slug}/merge/${pr.number}`);
    } catch (e) {
      setSubmitError(
        e instanceof ApiError
          ? e.message
          : "Couldn't create the merge request. Try again.",
      );
      setSubmitting(false);
    }
  }

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
        <Link
          to={
            slug
              ? `/organization/${slug}?tab=${encodeURIComponent("Merge requests")}`
              : "/organization"
          }
        >
          Merge requests
        </Link>
        <span className="crumb-sep">/</span>
        <span>Create</span>
      </nav>

      <header className="mr-head">
        <div className="mr-head-main">
          <div className="mr-title-row">
            <h1 className="mr-title">Create merge request</h1>
          </div>
          <p className="mr-sub">
            Create a merge request to propose and collaborate on your changes.
          </p>
        </div>
      </header>

      <BranchSelectorBar
        source={sourceInfo}
        target={targetInfo}
        sourceName={sourceBranch}
        targetName={targetBranch}
        branches={branches}
        editing={editingBranches}
        onToggleEditing={() => setEditingBranches((v) => !v)}
        onTarget={(name) => setPickedTarget(name)}
      />

      {duplicate && (
        <div className="panel-msg error cmr-duplicate">
          A merge request from <strong>{sourceBranch}</strong> into{" "}
          <strong>{targetBranch}</strong> already exists:{" "}
          <Link to={`/organization/${slug}/merge/${duplicate.number}`}>
            #{duplicate.number} — {duplicate.title}
          </Link>
        </div>
      )}

      <div className="repo-grid mr-grid">
        <div className="repo-col">
          <Tabs tab={tab} counts={counts} onSelect={setTab} />

          {tab === "overview" ? (
            <OverviewForm
              title={title}
              onTitle={(v) => {
                setTitleTouched(true);
                setTitleInput(v);
              }}
              description={description}
              onDescription={setDescription}
              reviewerOptions={reviewerOptions}
              onCreate={handleCreate}
              canSubmit={canSubmit}
              submitting={submitting}
              submitError={submitError}
            />
          ) : (
            <CommitsTab commits={uniqueCommits} slug={slug} ready={comparable} />
          )}
        </div>

        <aside className="repo-rail mr-rail">
          <ChangesSummaryCard
            commits={commitsCount}
            files={filesCount}
            additions={totals.additions}
            removals={totals.removals}
            ready={comparable}
          />
          <FilesChangedCard files={view?.files ?? []} ready={comparable} />
          <CommitsCard commits={uniqueCommits} slug={slug} ready={comparable} />
        </aside>
      </div>
    </div>
  );
}

// ---- Branch selector bar ----
function BranchSelectorBar({
  source,
  target,
  sourceName,
  targetName,
  branches,
  editing,
  onToggleEditing,
  onTarget,
}: {
  source?: BranchSummary;
  target?: BranchSummary;
  sourceName: string;
  targetName: string;
  branches: BranchSummary[];
  editing: boolean;
  onToggleEditing: () => void;
  onTarget: (name: string) => void;
}) {
  return (
    <section className="cmr-branchbar">
      <BranchBlock label="Source branch" branch={source} name={sourceName} icon={GitBranch} />
      <span className="cmr-branch-arrow" aria-hidden="true">
        <ArrowRight size={18} strokeWidth={1.9} />
      </span>
      <BranchBlock
        label="Target branch"
        branch={target}
        name={targetName}
        icon={GitPullRequest}
      />
      <div className="cmr-branch-edit">
        {editing && (
          <div className="cmr-branch-selects">
            <select
              className="select cmr-select"
              value={targetName}
              onChange={(e) => onTarget(e.target.value)}
              aria-label="Target branch"
            >
              {branches
                .filter((b) => b.name !== sourceName)
                .map((b) => (
                  <option key={b.name} value={b.name}>
                    {b.name}
                    {b.isDefault ? " (default)" : ""}
                  </option>
                ))}
            </select>
          </div>
        )}
        <button className="btn btn-ghost btn-sm" type="button" onClick={onToggleEditing}>
          {editing ? "Done" : "Change target branch"}
        </button>
      </div>
    </section>
  );
}

function BranchBlock({
  label,
  branch,
  name,
  icon: Icon,
}: {
  label: string;
  branch?: BranchSummary;
  name: string;
  icon: LucideIcon;
}) {
  const subject = branch?.lastCommitMessage;
  const shortSha = branch?.lastCommitHash;
  const author = branch?.lastCommitAuthor;
  return (
    <div className="cmr-branch-block">
      <span className="cmr-branch-label">{label}</span>
      <div className="cmr-branch-name-row">
        <span className="cmr-branch-ico">
          <Icon size={15} strokeWidth={1.9} />
        </span>
        <span className="cmr-branch-name">{name || "—"}</span>
      </div>
      <div className="cmr-branch-sub">
        {shortSha && subject ? (
          <>
            <span className="cmr-branch-sha">{shortSha}</span>
            <span className="cmr-branch-sep">·</span>
            <span className="cmr-branch-subject" title={subject}>
              {subject}
            </span>
            {author && (
              <>
                <span className="cmr-branch-sep">·</span>
                <span className="author cmr-branch-author">
                  <span className="author-av cmr-branch-av">{initials(author)}</span>
                  {author}
                </span>
              </>
            )}
          </>
        ) : (
          <span className="cmr-branch-empty">No commit information available</span>
        )}
      </div>
    </div>
  );
}

// ---- Tabs ----
function Tabs({
  tab,
  counts,
  onSelect,
}: {
  tab: CreateTab;
  counts: { commits: number };
  onSelect: (t: CreateTab) => void;
}) {
  const tabs: { key: CreateTab; label: string; count?: number }[] = [
    { key: "overview", label: "Overview" },
    { key: "commits", label: "Commits", count: counts.commits },
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

// ---- Overview tab (the form) ----
function OverviewForm({
  title,
  onTitle,
  description,
  onDescription,
  reviewerOptions,
  onCreate,
  canSubmit,
  submitting,
  submitError,
}: {
  title: string;
  onTitle: (v: string) => void;
  description: string;
  onDescription: (v: string) => void;
  reviewerOptions: { id: number; name: string; role: string }[];
  onCreate: (reviewerIds: number[]) => void;
  canSubmit: boolean;
  submitting: boolean;
  submitError: string | null;
}) {
  const [preview, setPreview] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Apply a markdown format to the textarea's current selection: inline marks
  // wrap it, line marks prefix each selected line, and blocks insert a
  // template. Keeps focus and reselects the affected text so formats chain.
  function applyFormat(kind: FormatKind) {
    const el = textareaRef.current;
    if (!el) return;
    const { selectionStart: start, selectionEnd: end, value } = el;
    const selected = value.slice(start, end);
    let next: string;
    let selFrom: number;
    let selTo: number;

    if (kind === "bold" || kind === "italic" || kind === "code") {
      const mark = kind === "bold" ? "**" : kind === "italic" ? "*" : "`";
      const inner = selected || "text";
      next = value.slice(0, start) + mark + inner + mark + value.slice(end);
      selFrom = start + mark.length;
      selTo = selFrom + inner.length;
    } else if (kind === "link") {
      const label = selected || "link text";
      const insert = `[${label}](url)`;
      next = value.slice(0, start) + insert + value.slice(end);
      // Select the "url" placeholder so the user types the address right away.
      selFrom = start + label.length + 3;
      selTo = selFrom + 3;
    } else if (kind === "ul" || kind === "ol") {
      // Prefix every line in the selection; operate on whole lines.
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const block = value.slice(lineStart, end);
      const lines = (block || "List item").split("\n");
      const marked = lines
        .map((l, i) => (kind === "ul" ? `- ${l}` : `${i + 1}. ${l}`))
        .join("\n");
      next = value.slice(0, lineStart) + marked + value.slice(end);
      selFrom = lineStart;
      selTo = lineStart + marked.length;
    } else {
      const table =
        "| Column | Column |\n| ------ | ------ |\n| Cell   | Cell   |";
      const prefix = start > 0 && value[start - 1] !== "\n" ? "\n\n" : "";
      next = value.slice(0, start) + prefix + table + "\n" + value.slice(end);
      selFrom = start + prefix.length;
      selTo = selFrom + table.length;
    }

    onDescription(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(selFrom, selTo);
    });
  }

  // Reviewers the author has added to this request. Starts empty; the menu
  // lists real project members.
  const [reviewers, setReviewers] = useState<number[]>([]);
  const [showReviewerMenu, setShowReviewerMenu] = useState(false);
  const chosen = reviewerOptions.filter((m) => reviewers.includes(m.id));
  const available = reviewerOptions.filter((m) => !reviewers.includes(m.id));

  return (
    <form
      className="cmr-form"
      onSubmit={(e) => {
        e.preventDefault();
        onCreate(reviewers);
      }}
    >
      {/* Title */}
      <div className="cmr-field">
        <div className="cmr-field-toprow">
          <label className="label" htmlFor="cmr-title">
            Title <span className="cmr-req">*</span>
          </label>
          <span className="cmr-counter">
            {title.length} / {TITLE_LIMIT}
          </span>
        </div>
        <input
          id="cmr-title"
          className="input"
          type="text"
          maxLength={TITLE_LIMIT}
          placeholder="Summarize this change"
          value={title}
          onChange={(e) => onTitle(e.target.value)}
        />
        <div className="field-hint cmr-hint">
          A clear title helps reviewers understand the purpose of this change.
        </div>
      </div>

      {/* Description */}
      <div className="cmr-field">
        <label className="label">Description</label>
        <div className="cmr-editor">
          <div className="cmr-toolbar">
            <div className="cmr-toolbar-group">
              <ToolbarButton
                label="Bold"
                icon={<Bold size={15} strokeWidth={2} />}
                disabled={preview}
                onClick={() => applyFormat("bold")}
              />
              <ToolbarButton
                label="Italic"
                icon={<Italic size={15} strokeWidth={2} />}
                disabled={preview}
                onClick={() => applyFormat("italic")}
              />
              <ToolbarButton
                label="Code"
                icon={<Code2 size={15} strokeWidth={2} />}
                disabled={preview}
                onClick={() => applyFormat("code")}
              />
              <ToolbarButton
                label="Link"
                icon={<Link2 size={15} strokeWidth={2} />}
                disabled={preview}
                onClick={() => applyFormat("link")}
              />
              <span className="cmr-toolbar-div" />
              <ToolbarButton
                label="Bulleted list"
                icon={<List size={15} strokeWidth={2} />}
                disabled={preview}
                onClick={() => applyFormat("ul")}
              />
              <ToolbarButton
                label="Numbered list"
                icon={<ListOrdered size={15} strokeWidth={2} />}
                disabled={preview}
                onClick={() => applyFormat("ol")}
              />
              <ToolbarButton
                label="Table"
                icon={<Table size={15} strokeWidth={2} />}
                disabled={preview}
                onClick={() => applyFormat("table")}
              />
            </div>
            <button
              type="button"
              className={`cmr-preview-toggle${preview ? " active" : ""}`}
              onClick={() => setPreview((v) => !v)}
            >
              {preview ? (
                <>
                  <Pencil size={14} strokeWidth={1.9} />
                  Edit
                </>
              ) : (
                <>
                  <Eye size={14} strokeWidth={1.9} />
                  Preview
                </>
              )}
            </button>
          </div>
          {preview ? (
            <div className="cmr-preview-body">
              {description.trim() ? (
                <div className="md-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {description}
                  </ReactMarkdown>
                </div>
              ) : (
                <span className="cmr-preview-empty">Nothing to preview yet.</span>
              )}
            </div>
          ) : (
            <textarea
              ref={textareaRef}
              className="cmr-textarea"
              placeholder="Describe what changed and why, so reviewers have the context they need."
              value={description}
              onChange={(e) => onDescription(e.target.value)}
            />
          )}
        </div>
        <div className="field-hint cmr-hint">Markdown is supported.</div>
      </div>

      {/* Reviewers */}
      <div className="cmr-field">
        <label className="label">Reviewers</label>
        <div className="cmr-chips">
          {chosen.map((m) => (
            <span className="cmr-chip" key={m.id}>
              <span className="author-av">{initials(m.name)}</span>
              {m.name}
              <button
                type="button"
                className="cmr-chip-x"
                aria-label={`Remove ${m.name}`}
                onClick={() =>
                  setReviewers((cur) => cur.filter((id) => id !== m.id))
                }
              >
                <X size={12} strokeWidth={2.2} />
              </button>
            </span>
          ))}
          <div className="cmr-add-wrap">
            <button
              type="button"
              className="cmr-add"
              onClick={() => setShowReviewerMenu((v) => !v)}
              disabled={available.length === 0}
            >
              <Plus size={14} strokeWidth={2} />
              Add reviewer
              <ChevronDown size={13} strokeWidth={2} />
            </button>
            {showReviewerMenu && available.length > 0 && (
              <div className="cmr-menu">
                {available.map((m) => (
                  <button
                    type="button"
                    className="cmr-menu-item"
                    key={m.id}
                    onClick={() => {
                      setReviewers((cur) => [...cur, m.id]);
                      setShowReviewerMenu(false);
                    }}
                  >
                    <span className="author-av">{initials(m.name)}</span>
                    <span className="cmr-menu-name">{m.name}</span>
                    <span className="cmr-menu-role">{m.role}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        {reviewerOptions.length === 0 && (
          <div className="field-hint cmr-hint">
            No project members are available to review yet.
          </div>
        )}
      </div>

      {/* Footer */}
      {submitError && <div className="panel-msg error cmr-submit-error">{submitError}</div>}
      <div className="cmr-footer">
        <button
          type="submit"
          className="btn btn-primary btn-sm"
          disabled={!canSubmit || submitting}
          title={
            canSubmit
              ? undefined
              : "Set a title and pick two different branches to compare"
          }
        >
          {submitting ? "Creating…" : "Create merge request"}
        </button>
      </div>
    </form>
  );
}

type FormatKind = "bold" | "italic" | "code" | "link" | "ul" | "ol" | "table";

function ToolbarButton({
  label,
  icon,
  disabled,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="cmr-tool"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
    >
      {icon}
    </button>
  );
}

// ---- Commits tab ----
function CommitsTab({
  commits,
  slug,
  ready,
}: {
  commits: Commit[];
  slug?: string;
  ready: boolean;
}) {
  if (!ready) {
    return (
      <section className="mr-section">
        <div className="mr-empty">
          Choose two different branches to compare their commits.
        </div>
      </section>
    );
  }
  if (commits.length === 0) {
    return (
      <section className="mr-section">
        <div className="mr-empty">No commits to merge between these branches.</div>
      </section>
    );
  }
  return (
    <section className="mr-section mr-commits">
      <ul className="mr-commits-rows">
        {commits.map((c) => {
          const inner = (
            <>
              <span className="mr-commit-main">
                <span className="mr-commit-msg">{c.message}</span>
                <span className="mr-commit-meta">
                  <span className="author">
                    <span className="author-av">{initials(c.author)}</span>
                    {c.author}
                  </span>
                  <span className="mr-commit-dot">·</span>
                  <span className="mr-commit-time">{timeAgo(c.at)}</span>
                </span>
              </span>
              <span className="mr-commit-right">
                <span className="mr-commit-sha">{c.hash}</span>
              </span>
            </>
          );
          return (
            <li key={c.sha}>
              {slug ? (
                <Link
                  className="mr-commit-row"
                  to={`/organization/${slug}/commit/${c.sha}`}
                >
                  {inner}
                </Link>
              ) : (
                <div className="mr-commit-row">{inner}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ---- Right rail ----
function ChangesSummaryCard({
  commits,
  files,
  additions,
  removals,
  ready,
}: {
  commits: number;
  files: number;
  additions: number;
  removals: number;
  ready: boolean;
}) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Changes summary</span>
      </div>
      {!ready ? (
        <div className="rail-empty">
          Select a source and target branch to preview the changes.
        </div>
      ) : (
        <div className="summary cmr-summary">
          <div className="summary-row">
            <span className="summary-ico">
              <GitCommitHorizontal size={16} strokeWidth={1.9} />
            </span>
            <span className="summary-value">{commits}</span>
            <span className="summary-label">
              {commits === 1 ? "commit" : "commits"}
            </span>
          </div>
          <div className="summary-row">
            <span className="summary-ico">
              <FileCode2 size={16} strokeWidth={1.9} />
            </span>
            <span className="summary-value">{files}</span>
            <span className="summary-label">
              {files === 1 ? "file changed" : "files changed"}
            </span>
          </div>
          <div className="cmr-diffstat">
            <span className="cmr-add-val">+{additions}</span>
            <span className="cmr-del-val">−{removals}</span>
          </div>
        </div>
      )}
    </section>
  );
}

function FilesChangedCard({ files, ready }: { files: string[]; ready: boolean }) {
  // Group by the leading path segment when files carry folder paths; files with
  // no path fall under a single unlabeled group. With no per-file +/− stats from
  // the backend, only the names are shown — never fabricated counts.
  const groups = useMemo(() => groupByFolder(files), [files]);
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Files changed ({files.length})</span>
        <button className="link-btn" type="button">
          View all files
        </button>
      </div>
      {!ready || files.length === 0 ? (
        <div className="rail-empty">No changed files to show.</div>
      ) : (
        <div className="rail-body">
          {groups.map((g) => (
            <div className="cmr-file-group" key={g.folder ?? "root"}>
              {g.folder && (
                <div className="cmr-file-folder">
                  <FolderClosed size={13} strokeWidth={1.8} />
                  <span>{g.folder}</span>
                </div>
              )}
              {g.files.map((file) => (
                <div className="rail-item cmr-file-item" key={file.full}>
                  <span className="cmr-file-ico">
                    <FileCode2 size={14} strokeWidth={1.8} />
                  </span>
                  <span className="cmr-file-name">{file.name}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// Split changed-file names into folder groups by their leading path segment.
// Names without a "/" land in a single unlabeled (folder: null) group so the
// common PLC case — bare entity names — renders as a flat list.
function groupByFolder(
  files: string[],
): { folder: string | null; files: { full: string; name: string }[] }[] {
  const order: (string | null)[] = [];
  const byFolder = new Map<string | null, { full: string; name: string }[]>();
  for (const full of files) {
    const slash = full.lastIndexOf("/");
    const folder = slash >= 0 ? full.slice(0, slash) : null;
    const name = slash >= 0 ? full.slice(slash + 1) : full;
    if (!byFolder.has(folder)) {
      byFolder.set(folder, []);
      order.push(folder);
    }
    byFolder.get(folder)!.push({ full, name });
  }
  return order.map((folder) => ({ folder, files: byFolder.get(folder)! }));
}

function CommitsCard({
  commits,
  slug,
  ready,
}: {
  commits: Commit[];
  slug?: string;
  ready: boolean;
}) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Commits ({commits.length})</span>
        <button className="link-btn" type="button">
          View all commits
        </button>
      </div>
      {!ready || commits.length === 0 ? (
        <div className="rail-empty">No commits to merge yet.</div>
      ) : (
        <ul className="cmr-timeline">
          {commits.map((c) => {
            const row = (
              <>
                <span className="cmr-tl-dot" aria-hidden="true" />
                <span className="cmr-tl-main">
                  <span className="cmr-tl-top">
                    <span className="cmr-tl-sha">{c.hash}</span>
                    <span className="cmr-tl-msg" title={c.message}>
                      {c.message}
                    </span>
                  </span>
                  <span className="cmr-tl-meta">
                    {c.author} · {timeAgo(c.at)}
                  </span>
                </span>
              </>
            );
            return (
              <li className="cmr-tl-item" key={c.sha}>
                {slug ? (
                  <Link className="cmr-tl-link" to={`/organization/${slug}/commit/${c.sha}`}>
                    {row}
                  </Link>
                ) : (
                  <span className="cmr-tl-link">{row}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
