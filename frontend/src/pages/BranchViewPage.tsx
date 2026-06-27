import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowDown,
  ArrowLeftRight,
  ArrowUp,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { FilesTable, initials } from "../components/FilesTable";
import { errorText, useProject } from "../api/queries";
import {
  type BranchInfo,
  type RepositoryDetail,
} from "../api/repository";
import { timeAgo } from "../lib/time";

export function BranchViewPage() {
  const params = useParams();
  const branchName = params.branch ? decodeURIComponent(params.branch) : "";
  const slug = params.slug;
  const { project, isPending, error } = useProject(params.slug);

  // The backend doesn't expose this rich detail yet; until it does, the page
  // renders empty states.
  const detail = null as RepositoryDetail | null;
  const info = useMemo<BranchInfo | null>(
    () => detail?.branches.find((b) => b.name === branchName) ?? null,
    [detail, branchName],
  );
  const files = detail?.fileList ?? [];

  return (
    <>
      <TopBar />
      <div className="app-scroll">
        {error ? (
          <div className="page-pad">
            <div className="panel-msg error">
              {errorText(error, "Failed to load branch.")}
            </div>
          </div>
        ) : isPending ? (
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
                {info.isProtected && (
                  <div className="repo-head-chips">
                    <span className="badge green">
                      <ShieldCheck size={14} strokeWidth={1.9} />
                      Protected
                    </span>
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
                      Behind
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
                      Ahead
                    </div>
                    <span className="stat-value">{info.ahead}</span>
                  </div>
                )}
              </div>
            )}

            <div className="branch-files">
              <div className="commit-bar">
                <span className="author">
                  <span className="author-av">{initials(info.author)}</span>
                  {info.author}
                </span>
                <span className="commit-bar-msg">{info.lastCommitMessage}</span>
                <span className="commit-bar-meta">
                  <span className="hash">{info.lastCommitHash}</span>
                  <span className="commit-bar-time">{timeAgo(info.at)}</span>
                </span>
              </div>
              {files.length === 0 ? (
                <div className="rcard-empty">No files on this branch yet.</div>
              ) : (
                <>
                  <div className="files-table">
                    <FilesTable files={files} slug={slug ?? ""} />
                  </div>
                  <div className="table-foot">
                    <span>
                      {files.length} files · {detail?.files.totalSize}
                    </span>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
