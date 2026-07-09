import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowDown,
  ArrowLeftRight,
  ArrowUp,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import { FilesTable, initials } from "../components/FilesTable";
import {
  errorText,
  useBranches,
  useCommits,
  useProject,
  useProjectFiles,
} from "../api/queries";
import { timeAgo } from "../lib/time";

export function BranchViewPage() {
  const params = useParams();
  const branchName = params.branch ? decodeURIComponent(params.branch) : "";
  const slug = params.slug;
  const { project, isPending, error } = useProject(params.slug);

  const branches = useBranches(project?.id);
  const info = useMemo(
    () => branches.data?.find((b) => b.name === branchName) ?? null,
    [branches.data, branchName],
  );
  // Ahead/behind counts are measured against the default branch; name it in
  // the labels so the comparison point is clear.
  const defaultBranchName = branches.data?.find((b) => b.isDefault)?.name;
  const filesQuery = useProjectFiles(project?.id, branchName);
  const files = filesQuery.data ?? [];
  const commitsQuery = useCommits(project?.id, branchName);
  const commits = commitsQuery.data ?? [];

  // The branch list resolves the branch; until it does (or if the project is
  // still loading) hold the loading state instead of flashing "not found".
  const loading = isPending || (project != null && branches.isPending);

  return (
      <div className="app-scroll">
        {error || branches.error ? (
          <div className="page-pad">
            <div className="panel-msg error">
              {errorText(error ?? branches.error, "Failed to load branch.")}
            </div>
          </div>
        ) : loading ? (
          <div className="page-pad">
            <div className="panel-msg">Loading branch…</div>
          </div>
        ) : !project || !info ? (
          <div className="page-pad">
            <div className="empty-state">
              <span className="empty-ico">
                <GitBranch size={24} strokeWidth={1.6} />
              </span>
              <h3>Branch not found</h3>
              <p>We couldn't find that branch in this project.</p>
              <Link to={`/projects/${slug}`} className="btn btn-primary btn-sm">
                Back to project
              </Link>
            </div>
          </div>
        ) : (
          <div className="mr-page">
            <nav className="crumb">
              <Link to="/projects">Repositories</Link>
              <span className="crumb-sep">/</span>
              <Link to={`/projects/${slug}`}>{project.name}</Link>
              <span className="crumb-sep">/</span>
              <span>{info.name}</span>
            </nav>

            <header className="mr-head">
              <span className="repo-ico repo-head-tile tone-blue">
                <GitBranch size={24} strokeWidth={1.9} />
              </span>
              <div className="mr-head-main">
                <div className="mr-title-row">
                  <h1 className="mr-title">{info.name}</h1>
                </div>
                {(info.isProtected || info.isDefault) && (
                  <div className="repo-head-chips">
                    {info.isDefault && <span className="mini-badge">Default</span>}
                    {info.isProtected && (
                      <span className="badge green">
                        <ShieldCheck size={14} strokeWidth={1.9} />
                        Protected
                      </span>
                    )}
                  </div>
                )}
              </div>
              <div className="mr-actions">
                <Link to="/compare" className="btn btn-outline btn-sm">
                  <ArrowLeftRight size={15} strokeWidth={1.8} />
                  Compare
                </Link>
              </div>
            </header>

            {(info.behind > 0 || info.ahead > 0) && (
              <div className="mr-meta stat-meta">
                {info.behind > 0 && (
                  <div className="mr-meta-card">
                    <div className="mr-meta-label">
                      <span className="mr-meta-ico">
                        <ArrowDown size={14} strokeWidth={1.8} />
                      </span>
                      Behind {defaultBranchName ?? "the default branch"}
                    </div>
                    <span className="stat-value">{info.behind}</span>
                  </div>
                )}
                {info.ahead > 0 && (
                  <div className="mr-meta-card">
                    <div className="mr-meta-label">
                      <span className="mr-meta-ico">
                        <ArrowUp size={14} strokeWidth={1.8} />
                      </span>
                      Ahead of {defaultBranchName ?? "the default branch"}
                    </div>
                    <span className="stat-value">{info.ahead}</span>
                  </div>
                )}
              </div>
            )}

            <div className="branch-files">
              {info.lastCommitHash && (
                <div className="commit-bar">
                  <span className="author">
                    <span className="author-av">
                      {initials(info.lastCommitAuthor ?? "")}
                    </span>
                    {info.lastCommitAuthor ?? "Unknown"}
                  </span>
                  <span className="commit-bar-msg">{info.lastCommitMessage}</span>
                  <span className="commit-bar-meta">
                    {info.lastCommitSha ? (
                      <Link
                        to={`/projects/${slug}/commit/${info.lastCommitSha}`}
                        className="hash crlink"
                      >
                        {info.lastCommitHash}
                      </Link>
                    ) : (
                      <span className="hash">{info.lastCommitHash}</span>
                    )}
                    {info.lastCommitAt && (
                      <span className="commit-bar-time">
                        {timeAgo(info.lastCommitAt)}
                      </span>
                    )}
                  </span>
                </div>
              )}
              {filesQuery.isPending ? (
                <div className="rcard-empty">Loading files…</div>
              ) : files.length === 0 ? (
                <div className="rcard-empty">No files on this branch yet.</div>
              ) : (
                <>
                  <div className="files-table">
                    <FilesTable files={files} slug={slug ?? ""} />
                  </div>
                  <div className="table-foot">
                    <span>
                      {files.length} {files.length === 1 ? "file" : "files"}
                    </span>
                  </div>
                </>
              )}
            </div>

            <div className="rcard">
              <div className="rcard-head">
                <span className="rcard-title">Commit history</span>
                {commits.length > 0 && (
                  <span className="mr-section-count">{commits.length}</span>
                )}
              </div>
              {commitsQuery.isPending ? (
                <div className="rcard-empty">Loading commits…</div>
              ) : commits.length === 0 ? (
                <div className="rcard-empty">No commits on this branch yet.</div>
              ) : (
                <table className="dtable">
                  <thead>
                    <tr>
                      <th>Commit</th>
                      <th>Message</th>
                      <th>Author</th>
                      <th>Committed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {commits.map((c) => (
                      <tr key={c.sha}>
                        <td>
                          <Link
                            to={`/projects/${slug}/commit/${c.sha}`}
                            className="hash crlink"
                          >
                            {c.hash}
                          </Link>
                        </td>
                        <td className="cell-strong">
                          <Link
                            to={`/projects/${slug}/commit/${c.sha}`}
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
                        <td className="muted-cell">{timeAgo(c.at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>
  );
}
