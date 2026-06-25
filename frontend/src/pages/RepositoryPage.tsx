import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Box,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Code2,
  Filter,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequestArrow,
  LayoutGrid,
  Plus,
  Search,
  Settings,
  Tag,
  Users,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { FilesTable } from "../components/FilesTable";
import { type Member, type ProjectRow } from "../api/projects";
import { type BranchInfo, type Commit, type RepositoryDetail } from "../api/repository";
import { type BranchSummary } from "../api/commits";
import { MR_STATUS_META, type ChangeRequestSummary } from "../api/mergeRequest";
import {
  errorText,
  useBranches,
  useChangeRequests,
  useCommits,
  useMembers,
  useProject,
} from "../api/queries";
import { formatDate, timeAgo } from "../lib/time";

const TABS = [
  { label: "Overview", icon: LayoutGrid },
  { label: "Code", icon: Code2 },
  { label: "Change requests", icon: GitPullRequestArrow },
  { label: "Settings", icon: Settings },
] as const;
type Tab = (typeof TABS)[number]["label"];

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function RepositoryPage() {
  const { slug } = useParams();
  const { isPending, error, project } = useProject(slug);
  const [tab, setTab] = useState<Tab>("Overview");

  // The backend doesn't expose this rich detail yet; until it does, the page
  // renders empty states.
  const [detail] = useState<RepositoryDetail | null>(null);

  // Change requests, commits, branches and members all come from the real
  // endpoints, keyed off the resolved project. Each stays disabled until the
  // project is known, then loads (and caches) on its own.
  const crs = useChangeRequests(project?.id).data ?? null;
  const commits =
    useCommits(project?.id, project?.branches[0] ?? "main").data ?? null;
  const branches = useBranches(project?.id).data ?? null;
  const members = useMembers(project?.id).data ?? null;

  return (
    <>
      <TopBar />
      <div className="app-scroll">
        {error ? (
          <div className="page-pad">
            <div className="panel-msg error">
              {errorText(error, "Failed to load repository.")}
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
              <p>We couldn't find a project with that name.</p>
              <Link to="/projects" className="btn btn-primary btn-sm">
                Back to projects
              </Link>
            </div>
          </div>
        ) : (
          <div className="repo-page">
            {/* breadcrumb */}
            <nav className="crumb">
              <Link to="/projects">Projects</Link>
              <span className="crumb-sep">/</span>
              <span>{project.name}</span>
            </nav>

            {/* header */}
            <header className="repo-head">
              <span className="repo-head-ico">
                <Box size={24} strokeWidth={2} />
              </span>
              <div className="repo-head-main">
                <div className="repo-head-title">
                  <h1>{project.name}</h1>
                </div>
                {detail?.description && <p className="repo-head-sub">{detail.description}</p>}
              </div>
            </header>

            {/* stat cards — overview only */}
            {tab === "Overview" && (
              <div className="repo-stats">
                <RepoStat
                  icon={GitBranch}
                  label="Branches"
                  value={branches ? String(branches.length) : undefined}
                />
                <RepoStat
                  icon={GitCommitHorizontal}
                  label="Last commit"
                  value={commits?.[0] ? timeAgo(commits[0].at) : undefined}
                  subRight
                  sub={
                    commits?.[0] && (
                      <span className="author">
                        <span className="author-av">{initials(commits[0].author)}</span>
                        {commits[0].author}
                      </span>
                    )
                  }
                />
                <RepoStat
                  icon={GitPullRequestArrow}
                  label="Open change requests"
                  value={
                    crs
                      ? String(crs.filter((cr) => cr.status !== "merged").length)
                      : undefined
                  }
                />
                <RepoStat
                  icon={Users}
                  label="Contributors"
                  value={members ? String(members.length) : undefined}
                />
              </div>
            )}

            {/* tabs */}
            <div className="repo-tabs">
              {TABS.map(({ label, icon: Icon }) => (
                <button
                  key={label}
                  className={`repo-tab${tab === label ? " active" : ""}`}
                  onClick={() => setTab(label)}
                >
                  <Icon size={15} strokeWidth={1.8} />
                  {label}
                </button>
              ))}
            </div>

            {tab === "Code" ? (
              <CodeView detail={detail} slug={slug ?? ""} />
            ) : tab === "Change requests" ? (
              <ChangeRequestsCard crs={crs} slug={slug ?? ""} />
            ) : tab !== "Overview" ? (
              <div className="panel-msg">{tab} isn't built yet.</div>
            ) : (
              <div className="repo-grid">
                <div className="repo-col">
                  <CommitsCard commits={commits} />
                  <BranchesCard branches={branches} project={project} />
                  <ChangeRequestsCard crs={crs} slug={slug ?? ""} />
                </div>
                <aside className="repo-rail">
                  <DetailsCard detail={detail} project={project} members={members} />
                  <TagsCard detail={detail} />
                </aside>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function RepoStat({
  icon: Icon,
  label,
  value,
  sub,
  subRight,
}: {
  icon: typeof Tag;
  label: string;
  value?: string;
  sub?: React.ReactNode;
  subRight?: boolean;
}) {
  const valueEl = (
    <span className={value ? "rstat-val" : "rstat-val empty"}>{value ?? "—"}</span>
  );
  return (
    <div className="rstat">
      <span className="rstat-ico">
        <Icon size={30} strokeWidth={2.2} />
      </span>
      {subRight ? (
        <div className="rstat-body rstat-split">
          <div className="rstat-textcol">
            <span className="rstat-label">{label}</span>
            {valueEl}
          </div>
          {sub}
        </div>
      ) : (
        <div className="rstat-body">
          <span className="rstat-label">{label}</span>
          {valueEl}
          {sub && <span className="rstat-sub">{sub}</span>}
        </div>
      )}
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

function CommitsCard({ commits }: { commits: Commit[] | null }) {
  return (
    <div className="rcard">
      <CardHead title="Recent commits" />
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
            </tr>
          </thead>
          <tbody>
            {commits.slice(0, 8).map((c) => (
              <tr key={c.hash}>
                <td>
                  <span className="hash">{c.hash}</span>
                </td>
                <td className="cell-strong">{c.message}</td>
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
        </table>
      )}
    </div>
  );
}

function BranchesCard({
  branches,
  project,
}: {
  branches: BranchSummary[] | null;
  project: ProjectRow;
}) {
  return (
    <div className="rcard">
      <CardHead title="Branches" />
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
              <th>Updated</th>
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
                      <span className="hash">{b.lastCommitHash}</span>{" "}
                      <span className="branch-msg">{b.lastCommitMessage}</span>
                    </>
                  ) : (
                    <span className="muted-cell">No commits</span>
                  )}
                </td>
                <td className="muted-cell">
                  {b.lastCommitAt ? timeAgo(b.lastCommitAt) : "—"}
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
  slug,
}: {
  crs: ChangeRequestSummary[] | null;
  slug: string;
}) {
  return (
    <div className="rcard">
      <CardHead title="Change requests" />
      {!crs || crs.length === 0 ? (
        <div className="rcard-empty">No change requests yet.</div>
      ) : (
        <table className="dtable">
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
  const rows = detail?.details ?? [
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
  branches: BranchInfo[];
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

function CodeView({ detail, slug }: { detail: RepositoryDetail | null; slug: string }) {
  const branches = detail?.branches ?? [];
  const defaultBranch =
    branches.find((b) => b.isDefault)?.name ?? branches[0]?.name ?? "";
  const [selected, setSelected] = useState(defaultBranch);

  if (!detail || branches.length === 0) {
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

  const info = branches.find((b) => b.name === selected) ?? branches[0];
  const files = detail.fileList;
  const commits = detail.commits.filter((c) => c.branch === info.name);

  return (
    <div className="repo-grid">
      <div className="repo-col code-view">
      <div className="code-bar">
        <BranchPicker
          branches={branches}
          selected={info.name}
          onSelect={setSelected}
        />
        <div className="code-search">
          <Search size={15} strokeWidth={1.8} />
          <input
            placeholder="Search files, tags, routines…"
            aria-label="Search files"
          />
          <Filter className="code-search-filter" size={15} strokeWidth={1.8} />
        </div>
      </div>

      <div className="table-wrap files-table">
        {files.length === 0 ? (
          <div className="rcard-empty">No files on this branch yet.</div>
        ) : (
          <>
            <FilesTable files={files} slug={slug} />
            <div className="table-foot code-foot">
              <span>
                {files.length} files · {detail.files.totalSize}
              </span>
              <span className="pager">
                Showing 1–{files.length} of {files.length}
                <button className="pager-btn" disabled aria-label="Previous page">
                  <ChevronLeft size={15} strokeWidth={1.9} />
                </button>
                <button className="pager-btn" disabled aria-label="Next page">
                  <ChevronRight size={15} strokeWidth={1.9} />
                </button>
              </span>
            </div>
          </>
        )}
      </div>

      <div className="code-section-head">
        <h3>
          Recent commits on <span className="mini-badge accent">{info.name}</span>
        </h3>
        <button className="link-btn">View all commits</button>
      </div>

      <div className="table-wrap files-table">
        {commits.length === 0 ? (
          <div className="rcard-empty">No commits on this branch yet.</div>
        ) : (
          <table className="dtable">
            <thead>
              <tr>
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
                    <span className="author">
                      <span className="author-av">{initials(c.author)}</span>
                      {c.author}
                    </span>
                  </td>
                  <td className="cell-strong">{c.message}</td>
                  <td className="muted-cell">{c.filesChanged ?? "—"}</td>
                  <td className="muted-cell">{timeAgo(c.at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      </div>

      <aside className="repo-rail code-rail">
        <AboutCodeCard />
      </aside>
    </div>
  );
}

function AboutCodeCard() {
  return (
    <section className="rcard">
      <CardHead title="About branches & commits" />
      <div className="about-body">
        <p className="about-intro">
          The Code view shows one branch at a time. Switch branch to update both
          the file tree and commits below.
        </p>
        <div className="about-item">
          <span className="about-ico">
            <GitBranch size={16} strokeWidth={1.9} />
          </span>
          <div>
            <div className="about-item-title">Branches</div>
            <div className="about-item-desc">
              An isolated line of work. Each branch keeps its own files and
              history until it's merged into another.
            </div>
          </div>
        </div>
        <div className="about-item">
          <span className="about-ico">
            <GitCommitHorizontal size={16} strokeWidth={1.9} />
          </span>
          <div>
            <div className="about-item-title">Commits</div>
            <div className="about-item-desc">
              A saved snapshot of changes. Recent commits show what changed most
              recently on the selected branch.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
