import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Check,
  ChevronDown,
  Code2,
  FileText,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequestArrow,
  History,
  Info,
  LayoutGrid,
  List,
  Network,
  Plus,
  Search,
  Settings,
  ShieldAlert,
  UploadCloud,
  X,
} from "lucide-react";
import { CommitTree } from "../components/CommitTree";
import { FilesTable } from "../components/FilesTable";
import { useAuth } from "../auth/AuthContext";
import {
  commitFiles,
  createBranch,
  type BranchSummary,
} from "../api/commits";
import { ApiError } from "../api/client";
import { errorText as apiErrorText } from "../api/queries";
import {
  type Member,
  type ProjectRow,
} from "../api/projects";
import {
  CR_META,
  type BranchInfo,
  type ChangeRequestRow,
  type Commit,
  type FileEntry,
  type RepositoryDetail,
} from "../api/repository";
import { MR_STATUS_META, type ChangeRequestSummary } from "../api/mergeRequest";
import {
  errorText,
  queryKeys,
  useBranches,
  useChangeRequests,
  useCommits,
  useMembers,
  useMergedPulls,
  useProject,
  useProjectFiles,
  useRepository,
} from "../api/queries";
import { formatDate, timeAgo } from "../lib/time";
import { RepoIcon } from "../lib/repoIcons";
import { initials } from "../lib/initials";
import { RepositorySettings } from "./RepositorySettings";
import { formatBytes } from "../lib/format";

const TABS = [
  { label: "Overview", icon: LayoutGrid },
  { label: "Files", icon: FileText },
  { label: "Merge requests", icon: GitPullRequestArrow },
  { label: "Settings", icon: Settings },
] as const;
type Tab = (typeof TABS)[number]["label"];


export function RepositoryPage() {
  const { slug } = useParams();
  const { isPending, error: projectError, project } = useProject(slug);

  const repoQuery = useRepository(slug);
  const detail = repoQuery.data ?? null;

  const crs = useChangeRequests(project?.id).data ?? null;
  const branches = useBranches(project?.id).data ?? null;
  // The repo's headline commits (Last commit strip, Overview commits card) are
  // the DEFAULT branch's — resolved by flag, not list position: branches[0]
  // sorts alphabetically and can be any feature branch.
  const defaultBranch = branches?.find((b) => b.isDefault)?.name ?? "main";
  const commits = useCommits(project?.id, defaultBranch).data ?? null;
  const members = useMembers(project?.id).data ?? null;

  const projectFatal = Boolean(projectError);

  return (
      <div className="app-scroll">
        {projectFatal ? (
          <div className="page-pad">
            <div className="panel-msg error">
              {errorText(projectError, "Failed to load repository.")}
            </div>
          </div>
        ) : isPending ? (
          <div className="page-pad">
            <div className="panel-msg">Loading repository…</div>
          </div>
        ) : !project ? (
          <div className="page-pad">
            <div className="empty-state">
              <span className="empty-ico">
                <Box size={24} strokeWidth={1.6} />
              </span>
              <h3>Repository not found</h3>
              <p>We couldn't find a repository with that name.</p>
              <Link to="/organization" className="btn btn-primary btn-sm">
                Back to repositories
              </Link>
            </div>
          </div>
        ) : (
          <RepositoryView
            detail={detail}
            project={project}
            commits={commits}
            branches={branches}
            crs={crs}
            members={members}
            slug={slug ?? ""}
          />
        )}
      </div>
  );
}

// The presentational repository view, independent of data loading. Holds the
// active tab and renders the header, meta strip, tabs and body.
function RepositoryView({
  detail,
  project,
  commits,
  branches,
  crs,
  members,
  slug,
}: {
  detail: RepositoryDetail | null;
  project: ProjectRow;
  commits: Commit[] | null;
  branches: BranchSummary[] | BranchInfo[] | null;
  crs: ChangeRequestSummary[] | null;
  members: Member[] | null;
  slug: string;
}) {
  // The URL is the single source of truth for the active tab: switching tabs
  // writes ?tab= and the tab is derived from it, so deep links ("View all
  // merge requests") always work and back/forward moves between tabs. An
  // unknown or missing value falls back to Overview (which carries no param).
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const tab: Tab = TABS.some((t) => t.label === requestedTab)
    ? (requestedTab as Tab)
    : "Overview";
  const setTab = (next: Tab) =>
    setSearchParams(next === "Overview" ? {} : { tab: next });
  // Overview's List/Tree toggle is URL state too (?view=tree), like the tab.
  const view = searchParams.get("view") === "tree" ? "tree" : "list";
  const setView = (v: "list" | "tree") =>
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (v === "tree") next.set("view", "tree");
      else next.delete("view");
      return next;
    });
  const [newBranchOpen, setNewBranchOpen] = useState(false);

  const { user } = useAuth();

  const description = detail?.description || project.description || "";
  const branchCount = detail?.branches?.length
    ? detail.branches.length
    : (branches?.length ?? project.branches?.length ?? null);

  return (
    <div className="mr-page">
      {/* breadcrumb */}
      <nav className="crumb">
        <Link to="/organization">{user?.organization ?? "Repositories"}</Link>
        <span className="crumb-sep">/</span>
        <span>{project.name}</span>
      </nav>

      {/* header */}
      <header className="mr-head repo-head">
        <RepoIcon icon={project.icon} slug={project.slug} size={27} className="repo-ico repo-head-tile" />
        <div className="mr-head-main">
          <div className="mr-title-row">
            <h1 className="mr-title">{project.name}</h1>
            {/* Every repository is visible to its members only; there are no
                public repositories yet, so the label is static. */}
            <span className="badge gray vis-pill">Private</span>
          </div>
          {description && <p className="mr-sub">{description}</p>}
        </div>
        <div className="mr-actions">
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={() => setNewBranchOpen(true)}
          >
            <GitBranch size={15} strokeWidth={1.8} />
            Create new branch
          </button>
          <Link
            to={`/organization/${project.slug}/merge-requests/new`}
            className="btn btn-primary btn-sm"
          >
            Create merge request
          </Link>
        </div>
      </header>

      {newBranchOpen && (
        <NewBranchDialog
          project={project}
          branches={branches}
          onClose={() => setNewBranchOpen(false)}
        />
      )}

      {/* meta strip — overview only */}
      {tab === "Overview" && (
        <MetaStrip
          detail={detail}
          commits={commits}
          crs={crs}
          branchCount={branchCount}
        />
      )}

      {/* tabs */}
      <nav className="pr-tabs repo-tabs2">
        {TABS.map(({ label, icon: Icon }) => (
          <button
            key={label}
            type="button"
            className={`pr-tab${tab === label ? " active" : ""}`}
            onClick={() => setTab(label)}
          >
            <Icon size={15} strokeWidth={1.8} />
            {label}
          </button>
        ))}
      </nav>

      {/* Keyed on the tab so switching re-mounts the body and replays the
          fade-in, instead of snapping between contents. */}
      <div className="tab-fade" key={tab}>
      {tab === "Files" ? (
        <CodeView detail={detail} project={project} slug={slug} />
      ) : tab === "Merge requests" ? (
        <ChangeRequestsCard
          crs={crs}
          detailCrs={detail?.changeRequests ?? null}
          slug={slug}
        />
      ) : tab === "Settings" ? (
        <RepositorySettings project={project} />
      ) : tab !== "Overview" ? (
        <div className="panel-msg">{tab} isn't built yet.</div>
      ) : (
        <div className="repo-grid">
          <div className="repo-col">
            <div className="seg overview-view-seg" role="tablist" aria-label="Overview view">
              <button
                type="button"
                className={`seg-btn${view === "list" ? " active" : ""}`}
                onClick={() => setView("list")}
              >
                <List size={14} strokeWidth={2} />
                List view
              </button>
              <button
                type="button"
                className={`seg-btn${view === "tree" ? " active" : ""}`}
                onClick={() => setView("tree")}
              >
                <Network size={14} strokeWidth={2} />
                Tree view
              </button>
            </div>
            {view === "tree" ? (
              <CommitTree
                slug={slug}
                projectId={project.id}
                defaultBranch={
                  (branches ?? []).find(
                    (b) => "isDefault" in b && b.isDefault,
                  )?.name ?? "main"
                }
                branches={branches ?? []}
              />
            ) : (
              <>
                <CommitsCard
                  commits={detail?.commits?.length ? detail.commits : commits}
                  slug={slug}
                />
                <BranchesCard
                  branches={detail?.branches?.length ? detail.branches : branches}
                  project={project}
                  slug={slug}
                />
                <ChangeRequestsCard
                  crs={crs}
                  detailCrs={detail?.changeRequests ?? null}
                  slug={slug}
                />
              </>
            )}
          </div>
          <aside className="repo-rail">
            <DetailsCard detail={detail} project={project} members={members} />
            <TagsCard detail={detail} />
          </aside>
        </div>
      )}
      </div>
    </div>
  );
}

// GitHub-style upload flow: files picked via "Add file" become one commit with
// a title and description, landing either directly on the current branch or on
// a fresh branch (then straight into the new-merge-request page). A protected
// current branch forces the new-branch path.
function UploadFilesDialog({
  project,
  slug,
  branch,
  branchProtected,
  existingBranches,
  initialFiles,
  onClose,
}: {
  project: ProjectRow;
  slug: string;
  branch: string;
  branchProtected: boolean;
  existingBranches: string[];
  initialFiles: File[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [files, setFiles] = useState<File[]>(initialFiles);
  // The default message is a placeholder, not a value, so typing replaces it
  // without the user having to clear the field; it's still what an untouched
  // commit gets on submit.
  const DEFAULT_MESSAGE = "Add files via upload";
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState<"direct" | "branch">(
    branchProtected ? "branch" : "direct",
  );
  // Default new-branch name the way GitHub does: <username>-patch-N, taking
  // the first N that doesn't collide with an existing branch.
  const stem = (user?.username ?? user?.email.split("@")[0] ?? "patch").replace(
    /[^a-zA-Z0-9._-]+/g,
    "-",
  );
  const firstFree = (() => {
    for (let n = 1; ; n += 1) {
      const name = `${stem}-patch-${n}`;
      if (!existingBranches.includes(name)) return name;
    }
  })();
  const [newBranch, setNewBranch] = useState(firstFree);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const moreRef = useRef<HTMLInputElement>(null);

  function addFiles(incoming: FileList) {
    const next = [...files];
    for (const f of Array.from(incoming)) {
      if (!next.some((e) => e.name === f.name && e.size === f.size)) next.push(f);
    }
    setFiles(next);
  }

  const target = mode === "branch" ? newBranch.trim() : branch;
  const commitMessage = title.trim() || DEFAULT_MESSAGE;
  const canCommit = files.length > 0 && target.length > 0 && !submitting;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canCommit) return;
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "branch") {
        try {
          await createBranch(project.id, target, branch);
        } catch (err) {
          // An existing branch is fine — commit to it; surface anything else.
          const exists = err instanceof ApiError && /exist/i.test(err.message);
          if (!exists) throw err;
        }
      }
      await commitFiles(project.id, {
        branch: target,
        message: commitMessage,
        description: description.trim(),
        files,
      });
      // The commit changed this project's branches, commits and files; drop
      // the cached queries so the page reflects the new state.
      qc.invalidateQueries({ queryKey: ["projects", project.id] });
      qc.invalidateQueries({ queryKey: queryKeys.projects });
      qc.invalidateQueries({ queryKey: queryKeys.repository(slug) });
      if (mode === "branch") {
        // Carry the commit title/description into the merge-request form so
        // the user doesn't retype them (they stay editable there).
        const qs = new URLSearchParams({ source: target, title: commitMessage });
        if (description.trim()) qs.set("description", description.trim());
        navigate(`/organization/${slug}/merge-requests/new?${qs}`);
      } else {
        onClose();
      }
    } catch (err) {
      setError(apiErrorText(err, "Couldn't upload the files. Try again."));
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <form
        className="modal modal-wide"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="modal-title">Commit changes</h3>
        {error && <div className="form-error">{error}</div>}

        <div className="upload-list">
          {files.map((f, i) => (
            <div className="upload-row" key={`${f.name}-${f.size}`}>
              <span className="file-name">
                <FileText size={15} strokeWidth={1.7} className="file-ico" />
                {f.name}
              </span>
              <span className="upload-size">{formatBytes(f.size)}</span>
              <button
                type="button"
                className="file-remove"
                aria-label={`Remove ${f.name}`}
                onClick={() => setFiles(files.filter((_, idx) => idx !== i))}
              >
                <X size={15} strokeWidth={2} />
              </button>
            </div>
          ))}
          <button
            type="button"
            className="link-btn"
            onClick={() => moreRef.current?.click()}
          >
            + Add more files
          </button>
          <input
            ref={moreRef}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        <div className="field">
          <label className="label" htmlFor="upload-title">
            Commit message <span className="req">*</span>
          </label>
          <input
            id="upload-title"
            className="input"
            placeholder={DEFAULT_MESSAGE}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div className="field">
          <label className="label" htmlFor="upload-desc">
            Extended description <span className="label-weak">(optional)</span>
          </label>
          <textarea
            id="upload-desc"
            className="textarea upload-desc"
            placeholder="Add an optional extended description…"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        {branchProtected && (
          <div className="rail-callout warn">
            <ShieldAlert size={15} strokeWidth={1.9} />
            <span>
              You can't commit to <strong>{branch}</strong> because it is a{" "}
              protected branch. A new branch will be created for this commit
              and you'll open a merge request. You can also switch to a
              non-protected branch in the Files view and add files there
              directly.
            </span>
          </div>
        )}

        <label
          className={`commit-choice${branchProtected ? " disabled" : ""}`}
        >
          <input
            type="radio"
            name="upload-dest"
            checked={mode === "direct"}
            disabled={branchProtected}
            onChange={() => setMode("direct")}
          />
          <span className="commit-choice-main">
            <GitCommitHorizontal size={15} strokeWidth={1.8} />
            Commit directly to the <strong>{branch}</strong> branch
          </span>
        </label>
        <label className="commit-choice">
          <input
            type="radio"
            name="upload-dest"
            checked={mode === "branch"}
            onChange={() => setMode("branch")}
          />
          <span className="commit-choice-main">
            <GitPullRequestArrow size={15} strokeWidth={1.8} />
            Create a <strong>new branch</strong> for this commit and start a
            merge request
          </span>
        </label>
        {mode === "branch" && (
          <div className="commit-choice-branch">
            <GitBranch size={14} strokeWidth={1.9} />
            <input
              className="input"
              value={newBranch}
              onChange={(e) => setNewBranch(e.target.value)}
              aria-label="New branch name"
              required
            />
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={!canCommit}
          >
            {submitting
              ? "Committing…"
              : mode === "branch"
                ? "Propose changes"
                : "Commit changes"}
          </button>
        </div>
      </form>
    </div>
  );
}

// Creates a branch off an existing start point via POST /projects/{id}/branches,
// then refreshes the project's branch data so the new branch shows up everywhere.
function NewBranchDialog({
  project,
  branches,
  onClose,
}: {
  project: ProjectRow;
  branches: BranchSummary[] | BranchInfo[] | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const branchNames = branches?.length
    ? branches.map((b) => b.name)
    : (project.branches ?? []);
  const defaultBranch =
    branches?.find((b) => b.isDefault)?.name ?? branchNames[0] ?? "main";

  const [name, setName] = useState("");
  const [startPoint, setStartPoint] = useState(defaultBranch);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await createBranch(project.id, name.trim(), startPoint);
      qc.invalidateQueries({ queryKey: queryKeys.branches(project.id) });
      qc.invalidateQueries({ queryKey: queryKeys.projects });
      onClose();
    } catch (err) {
      setError(apiErrorText(err, "Failed to create the branch."));
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <form
        className="modal"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="modal-title">Create new branch</h3>
        {error && <div className="form-error">{error}</div>}
        <div className="field">
          <label className="label" htmlFor="new-branch-name">
            Branch name
          </label>
          <input
            id="new-branch-name"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="feature/valve-sequencing"
            autoFocus
            required
          />
        </div>
        <div className="field">
          <label className="label" htmlFor="new-branch-source">
            Create from
          </label>
          <select
            id="new-branch-source"
            className="input"
            value={startPoint}
            onChange={(e) => setStartPoint(e.target.value)}
          >
            {branchNames.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </div>
        <div className="modal-actions">
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={!name.trim() || submitting}
          >
            {submitting ? "Creating…" : "Create branch"}
          </button>
        </div>
      </form>
    </div>
  );
}

function MetaStrip({
  detail,
  commits,
  crs,
  branchCount,
}: {
  detail: RepositoryDetail | null;
  commits: Commit[] | null;
  crs: ChangeRequestSummary[] | null;
  branchCount: number | null;
}) {
  const lastCommit = detail?.commits?.[0] ?? commits?.[0] ?? null;
  const openCount =
    detail?.openChangeRequests ??
    (crs ? crs.filter((c) => c.status !== "merged").length : null);

  return (
    <div className="mr-meta stat-meta repo-meta">
      <div className="mr-meta-card lc-card">
        <div className="lc-main">
          <div className="mr-meta-label">
            <span className="mr-meta-ico">
              <GitCommitHorizontal size={14} strokeWidth={1.8} />
            </span>
            Last commit
          </div>
          <span className="stat-value">{lastCommit ? timeAgo(lastCommit.at) : "—"}</span>
        </div>
        {lastCommit && (
          <span className="stat-sub lc-sub">
            <span className="author">
              <span className="author-av">{initials(lastCommit.author)}</span>
              by {lastCommit.author}
            </span>
            <span className="branch-tag">
              <GitBranch size={13} strokeWidth={2} />
              {lastCommit.branch}
            </span>
          </span>
        )}
      </div>
      <div className="mr-meta-card">
        <div className="mr-meta-label">
          <span className="mr-meta-ico">
            <GitPullRequestArrow size={14} strokeWidth={1.8} />
          </span>
          Open merge requests
        </div>
        <span className="stat-value">{openCount ?? "—"}</span>
      </div>
      <div className="mr-meta-card">
        <div className="mr-meta-label">
          <span className="mr-meta-ico">
            <GitBranch size={14} strokeWidth={1.8} />
          </span>
          Total branches
        </div>
        <span className="stat-value">{branchCount ?? "—"}</span>
      </div>
    </div>
  );
}

function CardHead({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="rcard-head">
      <span className="rcard-title">{title}</span>
      {action}
    </div>
  );
}

// A commit summary with the fields the row renders.
type CommitRow = Commit | {
  hash: string;
  sha: string;
  message: string;
  author: string;
  branch: string;
  at: string;
};

function CommitsCard({
  commits,
  slug,
}: {
  commits: CommitRow[] | null;
  slug: string;
}) {
  return (
    <div className="rcard">
      <CardHead
        title="Recent commits"
        action={
          <Link to={`/organization/${slug}/commits`} className="link-btn">
            View all commits
          </Link>
        }
      />
      {!commits || commits.length === 0 ? (
        <div className="rcard-empty">No commits yet.</div>
      ) : (
        <div className="dtable-scroll"><table className="dtable">
          <thead>
            <tr>
              <th>Commit</th>
              <th>Message</th>
              <th>Author</th>
              <th>Branch</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {commits.slice(0, 8).map((c) => (
              <tr key={c.hash}>
                <td>
                  <Link to={`/organization/${slug}/commit/${c.sha}`} className="hash crlink">
                    {c.hash}
                  </Link>
                </td>
                <td className="cell-strong">
                  <Link to={`/organization/${slug}/commit/${c.sha}`} className="crtitle">
                    {c.message}
                  </Link>
                </td>
                <td>
                  <span className="author">
                    <span className="author-av">{initials(c.author)}</span>
                    {c.author}
                  </span>
                </td>
                <td>
                  <span className="branch-tag">
                    <GitBranch size={13} strokeWidth={2} />
                    {c.branch}
                  </span>
                </td>
                <td className="muted-cell">{timeAgo(c.at)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}

function BranchesCard({
  branches,
  project,
  slug,
}: {
  branches: BranchSummary[] | BranchInfo[] | null;
  project: ProjectRow;
  slug: string;
}) {
  return (
    <div className="rcard">
      <CardHead
        title="Branches"
        action={
          <Link to={`/organization/${slug}/branches`} className="link-btn">
            View all branches
          </Link>
        }
      />
      {!branches ? (
        <div className="rcard-empty">Loading branches…</div>
      ) : branches.length === 0 ? (
        <div className="rcard-empty">
          {project.branches?.length
            ? project.branches.join(", ")
            : "No branches yet."}
        </div>
      ) : (
        <div className="dtable-scroll"><table className="dtable">
          <thead>
            <tr>
              <th>Branch</th>
              <th>Latest commit</th>
              <th>Latest activity</th>
              <th>Ahead / Behind</th>
            </tr>
          </thead>
          <tbody>
            {branches.map((b) => (
              <tr key={b.name}>
                <td>
                  <Link
                    to={`/organization/${slug}?tab=Files&branch=${encodeURIComponent(b.name)}`}
                    className="branch-name crlink"
                  >
                    <GitBranch size={13} strokeWidth={2} />
                    {b.name}
                  </Link>
                  {b.isDefault && (
                    <span className="mini-badge" style={{ marginLeft: 8 }}>
                      Default
                    </span>
                  )}
                  {!b.isDefault && "merged" in b && b.merged && (
                    <span className="mini-badge merged" style={{ marginLeft: 8 }}>
                      Merged
                    </span>
                  )}
                </td>
                <td>
                  {b.lastCommitHash ? (
                    <>
                      {"lastCommitSha" in b && b.lastCommitSha ? (
                        <Link
                          to={`/organization/${slug}/commit/${b.lastCommitSha}`}
                          className="hash crlink"
                        >
                          {b.lastCommitHash}
                        </Link>
                      ) : (
                        <span className="hash">{b.lastCommitHash}</span>
                      )}{" "}
                      <span className="branch-msg">{b.lastCommitMessage}</span>
                    </>
                  ) : (
                    <span className="muted-cell">No commits</span>
                  )}
                </td>
                <td className="muted-cell">
                  {"at" in b
                    ? timeAgo(b.at)
                    : b.lastCommitAt
                      ? timeAgo(b.lastCommitAt)
                      : "—"}
                </td>
                <td className="muted-cell">
                  {"ahead" in b ? (
                    b.ahead === 0 && b.behind === 0 ? (
                      "–"
                    ) : (
                      <span className="branch-ab">
                        <span className="ab-behind">
                          <ChevronDown size={12} strokeWidth={2} />
                          {b.behind}
                        </span>
                        <span className="ab-ahead">
                          <ChevronDown
                            size={12}
                            strokeWidth={2}
                            style={{ transform: "rotate(180deg)" }}
                          />
                          {b.ahead}
                        </span>
                      </span>
                    )
                  ) : (
                    "–"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}

function ChangeRequestsCard({
  crs,
  detailCrs,
  slug,
}: {
  crs: ChangeRequestSummary[] | null;
  detailCrs?: ChangeRequestRow[] | null;
  slug: string;
}) {
  const action = (
    <Link
      to={`/organization/${slug}?tab=${encodeURIComponent("Merge requests")}`}
      className="link-btn"
    >
      View all merge requests
    </Link>
  );

  if (detailCrs && detailCrs.length > 0) {
    return (
      <div className="rcard">
        <CardHead title="Merge requests" action={action} />
        <div className="dtable-scroll"><table className="dtable">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Author</th>
              <th>Status</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {detailCrs.map((cr) => {
              const m = CR_META[cr.status];
              const href = `/organization/${slug}/merge/${cr.id}`;
              return (
                <tr key={cr.id}>
                  <td>
                    <Link to={href} className="hash crlink">
                      {cr.id}
                    </Link>
                  </td>
                  <td className="cell-strong">
                    <Link to={href} className="crtitle">
                      {cr.title}
                    </Link>
                  </td>
                  <td>
                    <span className="author">
                      <span className="author-av">{initials(cr.author)}</span>
                      {cr.author}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${m.tone}`}>{m.label}</span>
                  </td>
                  <td className="muted-cell">{timeAgo(cr.at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table></div>
      </div>
    );
  }

  return (
    <div className="rcard">
      <CardHead title="Merge requests" action={action} />
      {!crs || crs.length === 0 ? (
        <div className="rcard-empty">
          No merge requests yet.{" "}
          <Link
            to={`/organization/${slug}/merge-requests/new`}
            className="link-btn"
          >
            Create a merge request
          </Link>
        </div>
      ) : (
        <div className="dtable-scroll"><table className="dtable">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Author</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {crs.map((cr) => {
              const m = MR_STATUS_META[cr.status];
              const href = `/organization/${slug}/merge/${cr.number}`;
              return (
                <tr key={cr.number}>
                  <td>
                    <Link to={href} className="hash crlink">
                      #{cr.number}
                    </Link>
                  </td>
                  <td className="cell-strong">
                    <Link to={href} className="crtitle">
                      {cr.title}
                    </Link>
                  </td>
                  <td>
                    <span className="author">
                      <span className="author-av">{initials(cr.author)}</span>
                      {cr.author}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${m.tone}`}>{m.label}</span>
                  </td>
                  <td className="muted-cell">{timeAgo(cr.createdAt)}</td>
                </tr>
              );
            })}
          </tbody>
        </table></div>
      )}
    </div>
  );
}

function DetailsCard({
  detail,
  project,
  members,
}: {
  detail: RepositoryDetail | null;
  project: ProjectRow;
  members: Member[] | null;
}) {
  const owner = members?.find((m) => m.role === "owner");
  const rows = [
    ...(detail?.details?.length
      ? detail.details
      : [
          { label: "Repository", value: project.slug },
          { label: "Owner", value: owner?.name ?? "—" },
          { label: "Created", value: formatDate(project.created_at) },
        ]),
  ];
  if (!rows.some((r) => r.label === "Last modified")) {
    rows.push({
      label: "Last modified",
      value: timeAgo(project.updated_at ?? project.created_at),
    });
  }
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Project details</span>
        <button className="link-btn" disabled title="Coming soon">Edit</button>
      </div>
      <dl className="kv">
        {rows.map((r) => (
          <div className="kv-row" key={r.label}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function TagsCard({ detail }: { detail: RepositoryDetail | null }) {
  const tags = detail?.tags ?? [];
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Tags</span>
        <button className="link-btn" disabled title="Coming soon">Edit</button>
      </div>
      {tags.length === 0 ? (
        <div className="rail-empty">No tags yet.</div>
      ) : (
        <div className="tag-chips">
          {tags.map((t) => (
            <span className={`tag-chip${t.tone ? ` ${t.tone}` : ""}`} key={t.label}>
              {t.label}
            </span>
          ))}
          <button className="tag-add" aria-label="Add tag" disabled title="Coming soon">
            <Plus size={13} strokeWidth={2} />
          </button>
        </div>
      )}
    </section>
  );
}

function BranchPicker({
  branches,
  selected,
  onSelect,
}: {
  branches: { name: string; isDefault?: boolean; merged?: boolean }[];
  selected: string;
  onSelect: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div className="branch-picker" ref={ref}>
      <button
        className="branch-switch"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <GitBranch size={15} strokeWidth={1.9} />
        <span className="branch-switch-name">{selected}</span>
        <ChevronDown size={15} strokeWidth={1.9} />
      </button>
      {open && (
        <div className="branch-menu">
          <div className="branch-menu-head">Switch branches</div>
          <div className="branch-menu-list">
            {branches.map((b) => (
              <button
                key={b.name}
                className={`branch-menu-item${b.name === selected ? " active" : ""}`}
                onClick={() => {
                  onSelect(b.name);
                  setOpen(false);
                }}
              >
                <GitBranch size={14} strokeWidth={1.8} />
                <span className="bmi-name">{b.name}</span>
                {b.isDefault && <span className="mini-badge accent">default</span>}
                {!b.isDefault && b.merged && (
                  <span className="mini-badge merged">merged</span>
                )}
                {b.name === selected && (
                  <Check className="bmi-check" size={14} strokeWidth={2.2} />
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CodeView({
  detail,
  project,
  slug,
}: {
  detail: RepositoryDetail | null;
  project: ProjectRow;
  slug: string;
}) {
  // Prefer the rich detail when it's populated; otherwise read branches and
  // commits from the live endpoints.
  const liveBranches = useBranches(project.id).data ?? null;
  const branchList: (BranchSummary | BranchInfo)[] = detail?.branches?.length
    ? detail.branches
    : (liveBranches ?? []);

  const defaultBranch =
    branchList.find((b) => b.isDefault)?.name ?? branchList[0]?.name ?? "";
  // The viewed branch is URL state (?branch=), so branch names elsewhere can
  // deep-link into this tab and back/forward moves between branches. Unknown
  // or missing values fall back to the default branch.
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedBranch = searchParams.get("branch");
  const branchName =
    requestedBranch && branchList.some((b) => b.name === requestedBranch)
      ? requestedBranch
      : defaultBranch;
  const setBranch = (name: string) =>
    setSearchParams({ tab: "Files", branch: name });
  // Files picked through "Add file"; non-null opens the commit dialog.
  const [uploadFiles, setUploadFiles] = useState<File[] | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);

  const liveCommits = useCommits(project.id, branchName || "main").data ?? null;
  // The branch whose contents are shown (falls back like `info` below does).
  const effectiveBranch =
    branchList.find((b) => b.name === branchName)?.name ?? branchList[0]?.name;
  // The real file listing at this branch — names, sizes and modified info come
  // from the repo, not from anything synthesized client-side.
  const liveFiles = useProjectFiles(project.id, effectiveBranch).data ?? null;
  // Merged pulls, to point a merged branch at the merge request that took it in.
  const mergedPulls = useMergedPulls(project.id).data ?? null;

  if (branchList.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-ico">
          <Code2 size={24} strokeWidth={1.6} />
        </span>
        <h3>No code yet</h3>
        <p>Import PLC logic to start tracking files and history.</p>
      </div>
    );
  }

  const info = branchList.find((b) => b.name === branchName) ?? branchList[0];
  // Each commit is a new snapshot of the repo's single L5X file, so it changes
  // exactly one file. (When repos hold multiple files this becomes a real count.)
  const commits: Commit[] = (
    detail?.commits?.length
      ? detail.commits.filter((c) => c.branch === info.name)
      : (liveCommits ?? [])
  ).map((c) => ({ ...c, filesChanged: c.filesChanged ?? 1 }));
  const files: FileEntry[] = liveFiles ?? [];
  // A merged branch is read-only in spirit: its work already landed, so new
  // uploads here are almost always a mistake — grey them out and say why.
  // (The `merged` flag exists only on the live branch summaries.)
  const isMerged =
    !info.isDefault && "merged" in info && Boolean(info.merged);
  const mergedPull = isMerged
    ? (mergedPulls?.find((p) => p.sourceBranch === info.name) ?? null)
    : null;
  const mergeTarget =
    mergedPull?.targetBranch ??
    branchList.find((b) => b.isDefault)?.name ??
    "main";
  // Ahead/behind only exists on the rich branch detail; the live branch list
  // doesn't expose it, so the divergence badges are hidden for live data.
  const divergence = "ahead" in info ? info : null;
  const upToDate = divergence ? divergence.ahead === 0 && divergence.behind === 0 : false;

  return (
    <div className="explorer">
      <div className="code-bar">
        <BranchPicker
          branches={branchList}
          selected={info.name}
          onSelect={setBranch}
        />
        {divergence && (
          <>
            {upToDate ? (
              <span className="badge green">Up to date</span>
            ) : (
              <span className="badge gray">Diverged</span>
            )}
            <span className="branch-ab">
              <span className="ab-ahead">
                <ChevronDown
                  size={12}
                  strokeWidth={2}
                  style={{ transform: "rotate(180deg)" }}
                />
                {divergence.ahead} ahead
              </span>
              <span className="ab-behind">
                <ChevronDown size={12} strokeWidth={2} />
                {divergence.behind} behind
              </span>
            </span>
          </>
        )}
        <div className="toolbar-search">
          <Search size={15} strokeWidth={1.8} />
          <input
            placeholder="Search files, folders, commits…"
            aria-label="Search files, folders, commits"
            disabled
            title="Search is coming soon"
          />
          <kbd className="search-kbd">⌘K</kbd>
        </div>
        <div className="code-bar-right">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={isMerged}
            title={
              isMerged
                ? `${info.name} has already been merged into ${mergeTarget} — create a new branch to add files.`
                : undefined
            }
            onClick={() => uploadRef.current?.click()}
          >
            <UploadCloud size={15} strokeWidth={1.8} />
            Add file
          </button>
          <input
            ref={uploadRef}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files?.length) setUploadFiles(Array.from(e.target.files));
              e.target.value = "";
            }}
          />
          <button type="button" className="btn btn-outline btn-sm">
            <History size={15} strokeWidth={1.8} />
            History
          </button>
        </div>
      </div>

      {uploadFiles && (
        <UploadFilesDialog
          project={project}
          slug={slug}
          branch={info.name}
          branchProtected={"isProtected" in info && Boolean(info.isProtected)}
          existingBranches={branchList.map((b) => b.name)}
          initialFiles={uploadFiles}
          onClose={() => setUploadFiles(null)}
        />
      )}

      {isMerged && (
        <div className="rail-callout merged-callout">
          <GitPullRequestArrow size={15} strokeWidth={1.9} />
          <span>
            <span className="mini-badge merged">Merged</span> This branch has
            been merged into <strong>{mergeTarget}</strong>
            {mergedPull ? (
              <>
                {" "}
                via{" "}
                <Link
                  to={`/organization/${slug}/merge/${mergedPull.number}`}
                  className="merged-callout-link"
                >
                  merge request #{mergedPull.number}
                </Link>
              </>
            ) : null}
            . Adding new files here is disabled — branch off {mergeTarget} for
            new work.
          </span>
        </div>
      )}

      <div className="rail-callout">
        <Info size={15} strokeWidth={1.9} />
        <span>
          You're viewing files and commits for branch <strong>{info.name}</strong>.
          Switching branches updates the repository contents and commits below.
        </span>
      </div>

      <div className="rcard">
        <CardHead title="Files" />
        {files.length === 0 ? (
          <div className="rcard-empty">No files on this branch yet.</div>
        ) : (
          <>
            <FilesTable
              files={files}
              projectId={project.id}
              refName={info.name}
            />
            <div className="table-foot">
              <span>
                {files.length} {files.length === 1 ? "file" : "files"}
              </span>
            </div>
          </>
        )}
      </div>

      <div className="rcard">
        <CardHead
          title={`Recent commits on ${info.name}`}
          action={
            <Link
              to={`/organization/${slug}/commits?branch=${encodeURIComponent(info.name)}`}
              className="link-btn"
            >
              View all on {info.name}
            </Link>
          }
        />
        {commits.length === 0 ? (
          <div className="rcard-empty">No commits on this branch yet.</div>
        ) : (
          <div className="dtable-scroll"><table className="dtable">
            <thead>
              <tr>
                <th>Commit</th>
                <th>Author</th>
                <th>Message</th>
                <th>Files changed</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {commits.map((c) => (
                <tr key={c.hash}>
                  <td>
                    <Link
                      to={`/organization/${slug}/commit/${c.sha}`}
                      className="hash crlink"
                    >
                      {c.hash}
                    </Link>
                  </td>
                  <td>
                    <span className="author">
                      <span className="author-av">{initials(c.author)}</span>
                      {c.author}
                    </span>
                  </td>
                  <td className="cell-strong">
                    <Link
                      to={`/organization/${slug}/commit/${c.sha}`}
                      className="crtitle"
                    >
                      {c.message}
                    </Link>
                  </td>
                  <td className="muted-cell">{c.filesChanged ?? "—"}</td>
                  <td className="muted-cell">{timeAgo(c.at)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}
