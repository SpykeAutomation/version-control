import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Box,
  Boxes,
  Calendar,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Database,
  Droplet,
  Flame,
  GitBranch,
  GitPullRequestArrow,
  type LucideIcon,
  MoreHorizontal,
  Plus,
  Search,
  SlidersHorizontal,
  Workflow,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { StatusBadge } from "../components/StatusBadge";
import { RailSection } from "../components/RailSection";
import { type ProjectRow, type RepoStatus } from "../api/projects";
import { errorText, useProjects } from "../api/queries";
import { timeAgo } from "../lib/time";

type SortKey = "updated" | "name" | "created";
type StatusFilter = "all" | RepoStatus;
type ControllerFilter = "all" | string;

const PAGE_SIZE = 6;

const lastActivity = (p: ProjectRow): string => p.updated_at ?? p.created_at;

const initials = (name: string): string => {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
};

// A repository's list icon and colour tone. Derived from the slug so each
// repository reads distinctly across the table and rail without depending on a
// backend category field. Tones map to the shared status palette.
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

export function ProjectsPage() {
  const { data: projects, isPending, error } = useProjects();

  const actions = (
    <>
      <button className="btn btn-outline btn-sm">
        <SlidersHorizontal size={15} strokeWidth={1.8} />
        Filters
      </button>
      <Link to="/onboarding" className="btn btn-primary btn-sm">
        <Plus size={16} strokeWidth={2} />
        New repository
      </Link>
    </>
  );

  return (
    <>
      <TopBar actions={actions} />
      <div className="app-scroll">
        {error ? (
          <div className="page-pad">
            <div className="panel-msg error">
              {errorText(error, "Failed to load repositories.")}
            </div>
          </div>
        ) : isPending ? (
          <div className="page-pad">
            <div className="panel-msg">Loading repositories…</div>
          </div>
        ) : (projects ?? []).length === 0 ? (
          <div className="page-pad">
            <EmptyProjects />
          </div>
        ) : (
          <ProjectsView projects={projects!} />
        )}
      </div>
    </>
  );
}

// The presentational repositories view, independent of data loading. Holds all
// view state (search, filters, sort, page) and the pure derivations off it.
function ProjectsView({ projects }: { projects: ProjectRow[] }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("updated");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [controller, setController] = useState<ControllerFilter>("all");
  const [page, setPage] = useState(1);

  const controllers = useMemo(
    () =>
      Array.from(
        new Set(
          projects.map((p) => p.controller).filter((c): c is string => Boolean(c)),
        ),
      ).sort(),
    [projects],
  );

  const totalControllers = useMemo(
    () =>
      new Set(
        projects.map((p) => p.controller).filter((c): c is string => Boolean(c)),
      ).size,
    [projects],
  );

  const openChanges = useMemo(
    () => projects.reduce((n, p) => n + (p.open_changes ?? 0), 0),
    [projects],
  );

  const totalBranches = useMemo(
    () => projects.reduce((n, p) => n + (p.branches?.length ?? 0), 0),
    [projects],
  );

  const visible = useMemo(() => {
    let rows = [...projects];
    if (status !== "all") rows = rows.filter((p) => p.status === status);
    if (controller !== "all") rows = rows.filter((p) => p.controller === controller);
    const q = query.trim().toLowerCase();
    if (q) {
      rows = rows.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.slug.toLowerCase().includes(q) ||
          (p.controller?.toLowerCase().includes(q) ?? false) ||
          (p.description?.toLowerCase().includes(q) ?? false),
      );
    }
    rows.sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      const ak = sort === "created" ? a.created_at : lastActivity(a);
      const bk = sort === "created" ? b.created_at : lastActivity(b);
      return ak < bk ? 1 : -1;
    });
    return rows;
  }, [projects, status, controller, query, sort]);

  const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageRows = visible.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  return (
    <div className="page-grid">
      <div className="page-main">
        <div className="page-header">
          <h1>Repositories</h1>
          <p>
            Manage PLC repositories, branches, releases, and commissioning
            context across your plant.
          </p>
        </div>

        <div className="mr-meta stat-meta">
          <div className="mr-meta-card">
            <div className="mr-meta-label">
              <span className="mr-meta-ico">
                <Database size={14} strokeWidth={1.8} />
              </span>
              Total repositories
            </div>
            <span className="stat-value">{projects.length}</span>
            <span className="stat-sub">Across organization</span>
          </div>
          <div className="mr-meta-card">
            <div className="mr-meta-label">
              <span className="mr-meta-ico">
                <Cpu size={14} strokeWidth={1.8} />
              </span>
              Controllers tracked
            </div>
            <span className="stat-value">{totalControllers}</span>
            <span className="stat-sub">Across all repositories</span>
          </div>
          <div className="mr-meta-card">
            <div className="mr-meta-label">
              <span className="mr-meta-ico">
                <GitPullRequestArrow size={14} strokeWidth={1.8} />
              </span>
              Open merge requests
            </div>
            <span className="stat-value">{openChanges}</span>
            <span className="stat-sub">Across all repositories</span>
          </div>
          <div className="mr-meta-card">
            <div className="mr-meta-label">
              <span className="mr-meta-ico">
                <GitBranch size={14} strokeWidth={1.8} />
              </span>
              Total branches
            </div>
            <span className="stat-value">{totalBranches}</span>
            <span className="stat-sub">Across all repositories</span>
          </div>
        </div>

        <div className="list-toolbar">
          <SelectControl
            value={controller}
            onChange={(v) => {
              setController(v);
              setPage(1);
            }}
            options={[
              ["all", "All controllers"],
              ...controllers.map((c) => [c, c] as [string, string]),
            ]}
          />
          <SelectControl
            value={status}
            onChange={(v) => {
              setStatus(v as StatusFilter);
              setPage(1);
            }}
            options={[
              ["all", "All statuses"],
              ["production", "Production"],
              ["commissioning", "Commissioning"],
              ["review", "Needs review"],
              ["draft", "Draft"],
            ]}
          />
          <SelectControl
            value={sort}
            onChange={(v) => setSort(v as SortKey)}
            icon={<Calendar size={15} strokeWidth={1.8} />}
            options={[
              ["updated", "Last activity"],
              ["name", "Name A–Z"],
              ["created", "Recently created"],
            ]}
          />
          <div className="toolbar-search">
            <Search size={15} strokeWidth={1.8} />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
              placeholder="Search by repository name…"
              aria-label="Search repositories"
            />
          </div>
        </div>

        {visible.length === 0 ? (
          <div className="panel-msg">No repositories match these filters.</div>
        ) : (
          <ProjectsTable
            rows={pageRows}
            total={visible.length}
            page={safePage}
            pageCount={pageCount}
            onPage={setPage}
          />
        )}
      </div>

      <aside className="page-rail">
        <RailSection title="Quick actions">
          <Link to="/onboarding" className="rail-item action">
            <span className="rail-ico">
              <Plus size={15} strokeWidth={1.8} />
            </span>
            <div className="rail-main">
              <div className="rail-label">New repository</div>
              <div className="rail-sub">Create a repository</div>
            </div>
            <ChevronRight className="rail-chev" size={15} strokeWidth={1.8} />
          </Link>
          <Link to="/compare" className="rail-item action">
            <span className="rail-ico">
              <GitPullRequestArrow size={15} strokeWidth={1.8} />
            </span>
            <div className="rail-main">
              <div className="rail-label">New merge request</div>
              <div className="rail-sub">Propose and review changes</div>
            </div>
            <ChevronRight className="rail-chev" size={15} strokeWidth={1.8} />
          </Link>
        </RailSection>

        <AboutRepositoriesCard />
      </aside>
    </div>
  );
}

function SelectControl({
  value,
  onChange,
  options,
  icon,
}: {
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  icon?: ReactNode;
}) {
  return (
    <div className={`toolbar-select-wrap${icon ? " has-ico" : ""}`}>
      {icon && <span className="toolbar-select-ico">{icon}</span>}
      <select
        className="toolbar-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
      <ChevronDown className="select-caret" size={15} strokeWidth={1.8} />
    </div>
  );
}

function ProjectsTable({
  rows,
  total,
  page,
  pageCount,
  onPage,
}: {
  rows: ProjectRow[];
  total: number;
  page: number;
  pageCount: number;
  onPage: (p: number) => void;
}) {
  const from = (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);
  return (
    <div className="table-wrap">
      <table className="dtable">
        <thead>
          <tr>
            <th>Repository</th>
            <th>Default branch</th>
            <th>Owner</th>
            <th>Last activity</th>
            <th>Status</th>
            <th>Activity</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              {/* Repository */}
              <td>
                <Link to={`/projects/${p.slug}`} className="repo-cell">
                  <RepoIcon slug={p.slug} size={18} className="repo-ico" />
                  <div>
                    <div className="repo-name">{p.name}</div>
                    {p.description && (
                      <div className="repo-sub">{p.description}</div>
                    )}
                  </div>
                </Link>
              </td>

              {/* Default branch */}
              <td>
                <span className="branch-tag">
                  <GitBranch size={14} strokeWidth={2} />
                  {p.branches?.[0] ?? "main"}
                </span>
              </td>

              {/* Owner */}
              <td>
                {p.owner ? (
                  <span className="author">
                    <span className="author-av">{initials(p.owner)}</span>
                    {p.owner}
                  </span>
                ) : (
                  <span className="cell-empty">—</span>
                )}
              </td>

              {/* Last activity */}
              <td>
                <div className="activity-cell">
                  <span className="ac-time">{timeAgo(lastActivity(p))}</span>
                  {p.last_activity_by && (
                    <span className="ac-who">{p.last_activity_by}</span>
                  )}
                </div>
              </td>

              {/* Status */}
              <td>
                {p.status ? (
                  <StatusBadge status={p.status} />
                ) : (
                  <span className="cell-empty">—</span>
                )}
              </td>

              {/* Activity counters */}
              <td>
                <div className="act-counts">
                  <span className="act-count">
                    <GitBranch size={13} strokeWidth={1.9} />
                    {p.branches?.length ?? 0}
                  </span>
                  <span
                    className={`act-count${
                      (p.open_changes ?? 0) > 0 ? " has" : ""
                    }`}
                  >
                    <GitPullRequestArrow size={13} strokeWidth={1.9} />
                    {p.open_changes ?? 0}
                  </span>
                </div>
              </td>

              {/* Kebab */}
              <td className="row-action">
                <button className="icon-btn" aria-label="More actions">
                  <MoreHorizontal size={16} strokeWidth={1.8} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="table-foot">
        <span>
          Showing {from} to {to} of {total} repositor
          {total === 1 ? "y" : "ies"}
        </span>
        <div className="pager">
          <button
            className="pager-btn"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
            aria-label="Previous page"
          >
            <ChevronLeft size={15} strokeWidth={1.8} />
          </button>
          {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              className={`pager-num${n === page ? " active" : ""}`}
              onClick={() => onPage(n)}
            >
              {n}
            </button>
          ))}
          <button
            className="pager-btn"
            disabled={page >= pageCount}
            onClick={() => onPage(page + 1)}
            aria-label="Next page"
          >
            <ChevronRight size={15} strokeWidth={1.8} />
          </button>
        </div>
      </div>
    </div>
  );
}

function AboutRepositoriesCard() {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">About repositories</span>
      </div>
      <div className="about-body">
        <p className="about-intro">
          A repository holds one PLC project's files and its full history of
          changes.
        </p>
        <div className="about-item">
          <span className="about-ico">
            <Database size={16} strokeWidth={1.9} />
          </span>
          <div>
            <div className="about-item-title">Repositories</div>
            <div className="about-item-desc">
              Each repository tracks a project's programs, routines, and tags,
              with every change recorded.
            </div>
          </div>
        </div>
        <div className="about-item">
          <span className="about-ico">
            <GitPullRequestArrow size={16} strokeWidth={1.9} />
          </span>
          <div>
            <div className="about-item-title">Collaboration</div>
            <div className="about-item-desc">
              Branches and merge requests let your team propose and review
              changes before they land.
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

function EmptyProjects() {
  return (
    <div className="empty-state">
      <span className="empty-ico">
        <Box size={24} strokeWidth={1.6} />
      </span>
      <h3>No repositories yet</h3>
      <p>Import PLC logic or create a repository to start tracking changes.</p>
      <Link to="/onboarding" className="btn btn-primary btn-sm">
        <Plus size={16} strokeWidth={2} />
        New repository
      </Link>
    </div>
  );
}
