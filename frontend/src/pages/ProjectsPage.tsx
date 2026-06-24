import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeftRight,
  Box,
  ChevronDown,
  Cpu,
  DownloadCloud,
  GitBranch,
  GitPullRequestArrow,
  Layers,
  MoreHorizontal,
  Plus,
  Search,
  SlidersHorizontal,
  Tag,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { RailSection } from "../components/RailSection";
import { listProjects, type ProjectRow, type RepoStatus } from "../api/projects";
import { ApiError } from "../api/client";
import { timeAgo } from "../lib/time";

type SortKey = "updated" | "name" | "created";
type StatusFilter = "all" | RepoStatus;

const lastActivity = (p: ProjectRow): string => p.updated_at ?? p.created_at;

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("updated");
  const [status, setStatus] = useState<StatusFilter>("all");

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Failed to load projects."),
      );
  }, []);

  const totalBranches = useMemo(
    () => (projects ?? []).reduce((n, p) => n + (p.branches?.length ?? 0), 0),
    [projects],
  );

  const recent = useMemo(
    () =>
      [...(projects ?? [])]
        .sort((a, b) => (lastActivity(a) < lastActivity(b) ? 1 : -1))
        .slice(0, 5),
    [projects],
  );

  const visible = useMemo(() => {
    let rows = [...(projects ?? [])];
    if (status !== "all") rows = rows.filter((p) => p.status === status);
    const q = query.trim().toLowerCase();
    if (q) {
      rows = rows.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.slug.toLowerCase().includes(q) ||
          (p.controller?.toLowerCase().includes(q) ?? false),
      );
    }
    rows.sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      const ak = sort === "created" ? a.created_at : lastActivity(a);
      const bk = sort === "created" ? b.created_at : lastActivity(b);
      return ak < bk ? 1 : -1;
    });
    return rows;
  }, [projects, status, query, sort]);

  const actions = (
    <>
      <button className="btn btn-outline btn-sm">
        <SlidersHorizontal size={15} strokeWidth={1.8} />
        Filters
      </button>
      <Link to="/onboarding" className="btn btn-primary btn-sm">
        <Plus size={16} strokeWidth={2} />
        New project
      </Link>
    </>
  );

  return (
    <>
      <TopBar actions={actions} />
      <div className="app-scroll">
        <div className="page-grid">
          <div className="page-main">
            <div className="page-header">
              <h1>Projects</h1>
              <p>
                Manage PLC projects, branches, releases, and commissioning
                context across your plant.
              </p>
            </div>

            <div className="stat-grid">
              <StatCard
                icon={Layers}
                label="Total projects"
                value={projects?.length ?? "—"}
              />
              <StatCard
                icon={GitBranch}
                label="Total branches"
                value={projects ? totalBranches : "—"}
              />
              <StatCard icon={GitPullRequestArrow} label="Open change requests" value="—" />
              <StatCard icon={Tag} label="Releases this month" value="—" />
            </div>

            {error ? (
              <div className="panel-msg error">{error}</div>
            ) : !projects ? (
              <div className="panel-msg">Loading projects…</div>
            ) : projects.length === 0 ? (
              <EmptyProjects />
            ) : (
              <>
                <div className="list-toolbar">
                  <SelectControl
                    value={status}
                    onChange={(v) => setStatus(v as StatusFilter)}
                    options={[
                      ["all", "All statuses"],
                      ["production", "Production"],
                      ["commissioning", "Commissioning"],
                      ["review", "Review"],
                      ["draft", "Draft"],
                    ]}
                  />
                  <SelectControl
                    value={sort}
                    onChange={(v) => setSort(v as SortKey)}
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
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search across projects…"
                      aria-label="Search projects"
                    />
                  </div>
                </div>

                {visible.length === 0 ? (
                  <div className="panel-msg">No projects match these filters.</div>
                ) : (
                  <ProjectsTable rows={visible} total={projects.length} />
                )}
              </>
            )}
          </div>

          <aside className="page-rail">
            <RailSection title="Recently updated">
              {recent.length === 0 ? (
                <div className="rail-empty">Nothing yet.</div>
              ) : (
                recent.map((p) => (
                  <div className="rail-item" key={p.id}>
                    <span className="rail-ico">
                      <Box size={15} strokeWidth={1.8} />
                    </span>
                    <div className="rail-main">
                      <div className="rail-label">{p.name}</div>
                      <div className="rail-sub">{timeAgo(lastActivity(p))}</div>
                    </div>
                  </div>
                ))
              )}
            </RailSection>

            <RailSection title="Quick actions">
              <Link to="/onboarding" className="rail-item action">
                <span className="rail-ico">
                  <Plus size={15} strokeWidth={1.8} />
                </span>
                <div className="rail-main">
                  <div className="rail-label">New project</div>
                  <div className="rail-sub">Start from an empty repository</div>
                </div>
              </Link>
              <div className="rail-item action disabled">
                <span className="rail-ico">
                  <DownloadCloud size={15} strokeWidth={1.8} />
                </span>
                <div className="rail-main">
                  <div className="rail-label">Import from controller</div>
                  <div className="rail-sub">Coming soon</div>
                </div>
              </div>
              <div className="rail-item action disabled">
                <span className="rail-ico">
                  <ArrowLeftRight size={15} strokeWidth={1.8} />
                </span>
                <div className="rail-main">
                  <div className="rail-label">Compare projects</div>
                  <div className="rail-sub">Coming soon</div>
                </div>
              </div>
            </RailSection>
          </aside>
        </div>
      </div>
    </>
  );
}

function SelectControl({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <div className="toolbar-select-wrap">
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

function ProjectsTable({ rows, total }: { rows: ProjectRow[]; total: number }) {
  return (
    <div className="table-wrap">
      <table className="dtable">
        <thead>
          <tr>
            <th>Project</th>
            <th>Controller</th>
            <th>Default branch</th>
            <th>Latest release</th>
            <th>Last activity</th>
            <th>Status</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td>
                <div className="repo-cell">
                  <span className="repo-ico">
                    <Box size={18} strokeWidth={2} />
                  </span>
                  <div>
                    <div className="repo-name">{p.name}</div>
                    <div className="repo-sub">{p.slug}</div>
                  </div>
                </div>
              </td>
              <td>
                {p.controller ? (
                  <div className="cell-controller">
                    <span className="cc-platform">
                      <Cpu
                        size={13}
                        strokeWidth={1.8}
                        style={{ marginRight: 6, verticalAlign: "-2px" }}
                      />
                      {p.controller}
                    </span>
                  </div>
                ) : (
                  <span className="cell-empty">Not set</span>
                )}
              </td>
              <td>
                <span className="branch-tag">
                  <GitBranch size={14} strokeWidth={2} />
                  {p.branches?.[0] ?? "main"}
                </span>
              </td>
              <td>
                {p.latest_release ? (
                  <span className="release-tag">
                    <Tag size={12} strokeWidth={1.8} />
                    {p.latest_release}
                  </span>
                ) : (
                  <span className="cell-empty">—</span>
                )}
              </td>
              <td>
                <div className="activity-cell">
                  <span className="ac-time">{timeAgo(lastActivity(p))}</span>
                  {p.last_activity_by && (
                    <span className="ac-who">{p.last_activity_by}</span>
                  )}
                </div>
              </td>
              <td>
                {p.status ? (
                  <StatusBadge status={p.status} />
                ) : (
                  <span className="cell-empty">—</span>
                )}
              </td>
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
          Showing {rows.length} of {total} project{total === 1 ? "" : "s"}
        </span>
      </div>
    </div>
  );
}

function EmptyProjects() {
  return (
    <div className="empty-state">
      <span className="empty-ico">
        <Box size={24} strokeWidth={1.6} />
      </span>
      <h3>No projects yet</h3>
      <p>Import PLC logic or create a project to start tracking changes.</p>
      <Link to="/onboarding" className="btn btn-primary btn-sm">
        <Plus size={16} strokeWidth={2} />
        New project
      </Link>
    </div>
  );
}
