import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ChevronDown, GitBranch } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { errorText, useBranches, useCommits, useProject } from "../api/queries";
import { timeAgo } from "../lib/time";

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

// A repository's commit history: every commit on the chosen branch with its
// author, branch and time. Rows link to the commit's review page. The branch
// can be preselected via ?branch=.
export function CommitsPage() {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const { project, isPending, error } = useProject(slug);
  const branches = useBranches(project?.id).data ?? null;

  const defaultBranch =
    searchParams.get("branch") ??
    branches?.find((b) => b.isDefault)?.name ??
    branches?.[0]?.name ??
    "";
  const [selected, setSelected] = useState(defaultBranch);
  // Branches load after the first render, so adopt the default once it arrives.
  useEffect(() => {
    if (!selected && defaultBranch) setSelected(defaultBranch);
  }, [selected, defaultBranch]);
  const branch = selected || defaultBranch;

  const commitsQuery = useCommits(project?.id, branch || "main");
  const commits = commitsQuery.data ?? null;

  return (
    <div className="app-scroll">
      {error ? (
        <div className="page-pad">
          <div className="panel-msg error">
            {errorText(error, "Failed to load commits.")}
          </div>
        </div>
      ) : isPending || !project ? (
        <div className="page-pad">
          <div className="panel-msg">Loading commits…</div>
        </div>
      ) : (
        <div className="mr-page">
          <nav className="crumb">
            <Link to="/organization">{user?.organization ?? "Repositories"}</Link>
            <span className="crumb-sep">/</span>
            <Link to={`/organization/${slug}`}>{project.name}</Link>
            <span className="crumb-sep">/</span>
            <span>Commits</span>
          </nav>

          <header className="mr-head">
            <div className="mr-head-main">
              <div className="mr-title-row">
                <h1 className="mr-title">Commits</h1>
              </div>
              <p className="mr-sub">
                The commit history of {project.name}. Pick a branch to see the
                commits it holds; click a commit to review it.
              </p>
            </div>
          </header>

          <div className="field commit-branch">
            <div className="select-wrap">
              <GitBranch className="select-lead" size={15} strokeWidth={1.8} />
              <select
                className="select has-lead"
                value={branch}
                onChange={(e) => setSelected(e.target.value)}
                aria-label="Branch"
              >
                {(branches ?? []).map((b) => (
                  <option key={b.name} value={b.name}>
                    {b.name}
                    {b.isDefault ? " (default)" : ""}
                  </option>
                ))}
              </select>
              <ChevronDown className="select-caret" size={16} strokeWidth={1.8} />
            </div>
          </div>

          <div className="rcard">
            {!commits ? (
              <div className="rcard-empty">Loading commits…</div>
            ) : commits.length === 0 ? (
              <div className="rcard-empty">No commits on this branch yet.</div>
            ) : (
              <div className="dtable-scroll"><table className="dtable">
                <thead>
                  <tr>
                    <th>Commit</th>
                    <th>Message</th>
                    <th>Author</th>
                    <th>Branch</th>
                    <th>Committed</th>
                  </tr>
                </thead>
                <tbody>
                  {commits.map((c) => (
                    <tr key={c.sha}>
                      <td>
                        <Link
                          to={`/organization/${slug}/commit/${c.sha}`}
                          className="hash crlink"
                        >
                          {c.hash}
                        </Link>
                      </td>
                      <td className="cell-strong">
                        <Link
                          to={`/organization/${slug}/commit/${c.sha}`}
                          className="crtitle"
                        >
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
                          {c.branch ?? branch}
                        </span>
                      </td>
                      <td className="muted-cell">{timeAgo(c.at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
