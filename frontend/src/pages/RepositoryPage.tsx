import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Box,
  Boxes,
  Check,
  ChevronDown,
  Code2,
  Droplet,
  FileText,
  Flame,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequestArrow,
  History,
  Info,
  LayoutGrid,
  type LucideIcon,
  MoreHorizontal,
  Plus,
  Search,
  Settings,
  Workflow,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { FilesTable } from "../components/FilesTable";
import { StatusBadge } from "../components/StatusBadge";
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
import { type BranchSummary } from "../api/commits";
import { MR_STATUS_META, type ChangeRequestSummary } from "../api/mergeRequest";
import {
  errorText,
  useBranches,
  useChangeRequests,
  useCommits,
  useCommitTree,
  useMembers,
  useProject,
  useRepository,
} from "../api/queries";
import { formatDate, timeAgo } from "../lib/time";

const TABS = [
  { label: "Overview", icon: LayoutGrid },
  { label: "Explore", icon: FileText },
  { label: "Merge requests", icon: GitPullRequestArrow },
  { label: "Settings", icon: Settings },
] as const;
type Tab = (typeof TABS)[number]["label"];

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

// A repository's icon and colour tone, derived from the slug so each repository
// reads distinctly without depending on a backend category field. Tones map to
// the shared status palette.
const REPO_VISUALS: { Icon: LucideIcon; tone: string }[] = [
  { Icon: Boxes, tone: "blue" },
  { Icon: Workflow, tone: "green" },
  { Icon: Droplet, tone: "violet" },
  { Icon: Flame, tone: "amber" },
  { Icon: Box, tone: "slate" },
];

function repoVisual(slug: string): { Icon: LucideIcon; tone: string } {
  let h = 0;
  for (let i = 0; i < slug.length; i += 1) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return REPO_VISUALS[h % REPO_VISUALS.length];
}

function RepoIcon({
  slug,
  size,
  className,
}: {
  slug: string;
  size: number;
  className: string;
}) {
  const { Icon, tone } = repoVisual(slug);
  return (
    <span className={`${className} tone-${tone}`}>
      <Icon size={size} strokeWidth={1.9} />
    </span>
  );
}

export function RepositoryPage() {
  const { slug } = useParams();
  const { isPending, error: projectError, project } = useProject(slug);

  const repoQuery = useRepository(slug);
  const detail = repoQuery.data ?? null;

  const crs = useChangeRequests(project?.id).data ?? null;
  const commits =
    useCommits(project?.id, project?.branches[0] ?? "main").data ?? null;
  const branches = useBranches(project?.id).data ?? null;
  const members = useMembers(project?.id).data ?? null;

  const projectFatal = Boolean(projectError);

  return (
    <>
      <TopBar />
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
              <Link to="/projects" className="btn btn-primary btn-sm">
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
    </>
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
  const [tab, setTab] = useState<Tab>("Overview");

  const description = detail?.description || project.description || "";
  const branchCount = detail?.branches?.length
    ? detail.branches.length
    : (branches?.length ?? project.branches?.length ?? null);

  return (
    <div className="mr-page">
      {/* breadcrumb */}
      <nav className="crumb">
        <Link to="/projects">Repositories</Link>
        <span className="crumb-sep">/</span>
        <span>{project.name}</span>
      </nav>

      {/* header */}
      <header className="mr-head">
        <RepoIcon slug={project.slug} size={24} className="repo-ico repo-head-tile" />
        <div className="mr-head-main">
          <div className="mr-title-row">
            <h1 className="mr-title">{project.name}</h1>
          </div>
          {description && <p className="mr-sub">{description}</p>}
          {detail?.status && (
            <div className="repo-head-chips">
              <StatusBadge status={detail.status} />
            </div>
          )}
        </div>
        <div className="mr-actions">
          <Link
            to={`/projects/${project.slug}/merge-requests/new`}
            className="btn btn-primary btn-sm"
          >
            Create merge request
          </Link>
        </div>
      </header>

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

      {tab === "Explore" ? (
        <CodeView detail={detail} project={project} slug={slug} />
      ) : tab === "Merge requests" ? (
        <ChangeRequestsCard
          crs={crs}
          detailCrs={detail?.changeRequests ?? null}
          slug={slug}
        />
      ) : tab !== "Overview" ? (
        <div className="panel-msg">{tab} isn't built yet.</div>
      ) : (
        <div className="repo-grid">
          <div className="repo-col">
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
          </div>
          <aside className="repo-rail">
            <DetailsCard detail={detail} project={project} members={members} />
            <TagsCard detail={detail} />
          </aside>
        </div>
      )}
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
          <Link to={`/projects/${slug}/commit`} className="link-btn">
            View all commits
          </Link>
        }
      />
      {!commits || commits.length === 0 ? (
        <div className="rcard-empty">No commits yet.</div>
      ) : (
        <table className="dtable">
          <thead>
            <tr>
              <th>Commit</th>
              <th>Message</th>
              <th>Author</th>
              <th>Branch</th>
              <th>Updated</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {commits.slice(0, 8).map((c) => (
              <tr key={c.hash}>
                <td>
                  <Link to={`/projects/${slug}/commit/${c.sha}`} className="hash crlink">
                    {c.hash}
                  </Link>
                </td>
                <td className="cell-strong">
                  <Link to={`/projects/${slug}/commit/${c.sha}`} className="crtitle">
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
                <td className="row-action">
                  <button className="icon-btn" aria-label="More actions">
                    <MoreHorizontal size={16} strokeWidth={1.8} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
          <Link
            to={`/projects/${slug}/tree/${project.branches?.[0] ?? "main"}`}
            className="link-btn"
          >
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
        <table className="dtable">
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
                  <span className="branch-name">
                    <GitBranch size={13} strokeWidth={2} />
                    {b.name}
                    {b.isDefault && <span className="mini-badge">Default</span>}
                  </span>
                </td>
                <td>
                  {b.lastCommitHash ? (
                    <>
                      {"lastCommitSha" in b && b.lastCommitSha ? (
                        <Link
                          to={`/projects/${slug}/commit/${b.lastCommitSha}`}
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
        </table>
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
    <Link to="/changes" className="link-btn">
      View all merge requests
    </Link>
  );

  if (detailCrs && detailCrs.length > 0) {
    return (
      <div className="rcard">
        <CardHead title="Merge requests" action={action} />
        <table className="dtable">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Author</th>
              <th>Status</th>
              <th>Updated</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {detailCrs.map((cr) => {
              const m = CR_META[cr.status];
              const href = `/projects/${slug}/merge/${cr.id}`;
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
                  <td className="row-action">
                    <button className="icon-btn" aria-label="More actions">
                      <MoreHorizontal size={16} strokeWidth={1.8} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="rcard">
      <CardHead title="Merge requests" action={action} />
      {!crs || crs.length === 0 ? (
        <div className="rcard-empty">No merge requests yet.</div>
      ) : (
        <table className="dtable">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Author</th>
              <th>Status</th>
              <th>Created</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {crs.map((cr) => {
              const m = MR_STATUS_META[cr.status];
              const href = `/projects/${slug}/merge/${cr.number}`;
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
                  <td className="row-action">
                    <button className="icon-btn" aria-label="More actions">
                      <MoreHorizontal size={16} strokeWidth={1.8} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
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
  const rows = detail?.details?.length
    ? detail.details
    : [
        { label: "Repository", value: project.slug },
        { label: "Owner", value: owner?.name ?? "—" },
        { label: "Created", value: formatDate(project.created_at) },
      ];
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">Project details</span>
        <button className="link-btn">Edit</button>
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
        <button className="link-btn">Edit</button>
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
          <button className="tag-add" aria-label="Add tag">
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
  branches: { name: string; isDefault?: boolean }[];
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
  const [selected, setSelected] = useState(defaultBranch);
  // Branches load after the first render, so adopt the default once it arrives.
  useEffect(() => {
    if (!selected && defaultBranch) setSelected(defaultBranch);
  }, [selected, defaultBranch]);
  const branchName = selected || defaultBranch;

  const liveCommits = useCommits(project.id, branchName || "main").data ?? null;
  // The controller name (the L5X file's name) comes from the organizer tree at
  // the branch's latest commit.
  const tree = useCommitTree(project.id, liveCommits?.[0]?.sha).data ?? null;

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
  // A repo holds one or more L5X/ACD files; today each repo stores a single
  // controller, so list that one file. Rendered as a list so it scales when a
  // repo holds more. Name comes from the controller; "modified" from the latest
  // commit on this branch.
  const controllerName = tree?.root.label;
  const latestCommit = commits[0];
  const files: FileEntry[] =
    controllerName && latestCommit
      ? [
          {
            name: `${controllerName}.L5X`,
            kind: "controller",
            size: "—",
            modifiedAt: latestCommit.at,
            modifiedBy: latestCommit.author,
          },
        ]
      : [];
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
          onSelect={setSelected}
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
          />
          <kbd className="search-kbd">⌘K</kbd>
        </div>
        <div className="code-bar-right">
          <button type="button" className="btn btn-outline btn-sm">
            <History size={15} strokeWidth={1.8} />
            History
          </button>
        </div>
      </div>

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
            <FilesTable files={files} slug={slug} />
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
            <Link to={`/projects/${slug}/commit`} className="link-btn">
              View all on {info.name}
            </Link>
          }
        />
        {commits.length === 0 ? (
          <div className="rcard-empty">No commits on this branch yet.</div>
        ) : (
          <table className="dtable">
            <thead>
              <tr>
                <th>Commit</th>
                <th>Author</th>
                <th>Message</th>
                <th>Files changed</th>
                <th>Date</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {commits.map((c) => (
                <tr key={c.hash}>
                  <td>
                    <Link
                      to={`/projects/${slug}/commit/${c.sha}`}
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
                      to={`/projects/${slug}/commit/${c.sha}`}
                      className="crtitle"
                    >
                      {c.message}
                    </Link>
                  </td>
                  <td className="muted-cell">{c.filesChanged ?? "—"}</td>
                  <td className="muted-cell">{timeAgo(c.at)}</td>
                  <td className="row-action">
                    <button className="icon-btn" aria-label="More actions">
                      <MoreHorizontal size={16} strokeWidth={1.8} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
