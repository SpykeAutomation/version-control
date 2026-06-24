import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowDown,
  ArrowLeftRight,
  ArrowUp,
  ChevronDown,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { FilesTable, initials } from "../components/FilesTable";
import { listProjects, type ProjectRow } from "../api/projects";
import { ApiError } from "../api/client";
import type { BranchInfo, RepositoryDetail } from "../api/repository";
import { timeAgo } from "../lib/time";

export function BranchViewPage() {
  const { slug, branch } = useParams();
  const branchName = branch ? decodeURIComponent(branch) : "";
  const [projects, setProjects] = useState<ProjectRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Failed to load branch."),
      );
  }, []);

  const project = useMemo(
    () => projects?.find((p) => p.slug === slug) ?? null,
    [projects, slug],
  );

  // The backend doesn't expose this rich detail yet; until it does, the page
  // renders empty states.
  const [detail] = useState<RepositoryDetail | null>(null);
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
            <div className="panel-msg error">{error}</div>
          </div>
        ) : !projects ? (
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
          <div className="repo-page">
            <nav className="crumb">
              <Link to="/projects">Projects</Link>
              <span className="crumb-sep">/</span>
              <Link to={`/projects/${slug}`}>{project.name}</Link>
              <span className="crumb-sep">/</span>
              <span>{info.name}</span>
            </nav>

            <div className="branch-bar">
              <button className="branch-switch">
                <GitBranch size={15} strokeWidth={1.9} />
                {info.name}
                <ChevronDown size={15} strokeWidth={1.9} />
              </button>
              {info.isProtected && (
                <span className="br-status protected">
                  <ShieldCheck size={14} strokeWidth={1.9} />
                  Protected
                </span>
              )}
              {(info.behind > 0 || info.ahead > 0) && (
                <span className="branch-rel">
                  {info.behind > 0 && (
                    <span className="ba-part">
                      <ArrowDown size={12} strokeWidth={2} />
                      {info.behind} behind
                    </span>
                  )}
                  {info.ahead > 0 && (
                    <span className="ba-part">
                      <ArrowUp size={12} strokeWidth={2} />
                      {info.ahead} ahead
                    </span>
                  )}
                </span>
              )}
              <Link
                to="/compare"
                className="btn btn-outline btn-sm branch-compare"
              >
                <ArrowLeftRight size={15} strokeWidth={1.8} />
                Compare
              </Link>
            </div>

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
