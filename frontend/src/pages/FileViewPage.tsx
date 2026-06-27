import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Download,
  FileCode2,
  FileText,
  GitBranch,
  Monitor,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { RungView } from "../components/Ladder";
import { errorText, useProject } from "../api/queries";
import {
  FILE_KIND_LABEL,
  type FileEntry,
  type RepositoryDetail,
} from "../api/repository";
import { timeAgo } from "../lib/time";

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function FileViewPage() {
  const params = useParams();
  const name = params.fileName ? decodeURIComponent(params.fileName) : "";
  const slug = params.slug;
  const { project, isPending, error } = useProject(params.slug);

  // The backend doesn't expose this rich detail yet; until it does, the page
  // renders empty states.
  const detail = null as RepositoryDetail | null;
  const file = useMemo(
    () => detail?.fileList.find((f) => f.name === name) ?? null,
    [detail, name],
  );

  return (
    <>
      <TopBar />
      <div className="app-scroll">
        {error ? (
          <div className="page-pad">
            <div className="panel-msg error">
              {errorText(error, "Failed to load file.")}
            </div>
          </div>
        ) : isPending ? (
          <div className="page-pad">
            <div className="panel-msg">Loading file…</div>
          </div>
        ) : !project || !file ? (
          <div className="page-pad">
            <div className="empty-state">
              <span className="empty-ico">
                <FileCode2 size={24} strokeWidth={1.6} />
              </span>
              <h3>File not found</h3>
              <p>We couldn't find that file in this project.</p>
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
              <span>{file.name}</span>
            </nav>

            <FileHeader file={file} />
            <FileBody file={file} />
          </div>
        )}
      </div>
    </>
  );
}

function FileHeader({ file }: { file: FileEntry }) {
  return (
    <>
      <header className="mr-head">
        <span className="repo-ico repo-head-tile tone-slate">
          <FileCode2 size={24} strokeWidth={1.9} />
        </span>
        <div className="mr-head-main">
          <div className="mr-title-row">
            <h1 className="mr-title">{file.name}</h1>
          </div>
        </div>
        <div className="mr-actions">
          <button className="btn btn-outline btn-sm">
            <Download size={15} strokeWidth={1.8} />
            Download
          </button>
        </div>
      </header>

      <div className="mr-meta stat-meta">
        <div className="mr-meta-card">
          <div className="mr-meta-label">
            <span className="mr-meta-ico">
              <FileText size={14} strokeWidth={1.8} />
            </span>
            Kind
          </div>
          <span className="stat-value">{FILE_KIND_LABEL[file.kind]}</span>
        </div>
        <div className="mr-meta-card">
          <div className="mr-meta-label">
            <span className="mr-meta-ico">
              <FileText size={14} strokeWidth={1.8} />
            </span>
            Size
          </div>
          <span className="stat-value">{file.size}</span>
        </div>
        <div className="mr-meta-card">
          <div className="mr-meta-label">
            <span className="mr-meta-ico">
              <FileText size={14} strokeWidth={1.8} />
            </span>
            Last modified
          </div>
          <span className="stat-value">{timeAgo(file.modifiedAt)}</span>
          <span className="stat-sub">
            <span className="author">
              <span className="author-av">{initials(file.modifiedBy)}</span>
              by {file.modifiedBy}
            </span>
          </span>
        </div>
      </div>
    </>
  );
}

function FileBody({ file }: { file: FileEntry }) {
  const c = file.content;
  if (!c) {
    return <div className="panel-msg">No preview is available for this file.</div>;
  }

  if (c.type === "ladder") {
    return (
      <div className="fv-routines">
        {c.routines.map((r) => (
          <section className="rcard" key={r.name}>
            <div className="rcard-head">
              <span className="rcard-title">
                <GitBranch
                  size={14}
                  strokeWidth={1.9}
                  style={{ verticalAlign: "-2px", marginRight: 8, color: "var(--ink3)" }}
                />
                {r.name}
              </span>
              <span className="fv-rung-count">
                {r.rungs.length} rung{r.rungs.length === 1 ? "" : "s"}
              </span>
            </div>
            <div className="fv-rungs">
              {r.rungs.map((rung) => (
                <RungView
                  key={rung.number}
                  rung={rung}
                  showNumbers
                  showHighlight={false}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    );
  }

  if (c.type === "table") {
    return (
      <div className="table-wrap files-table">
        <table className="dtable">
          <thead>
            <tr>
              {c.columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {c.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className={j === 0 ? "fv-key" : "muted-cell"}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="table-foot">
          <span>{c.rows.length} rows</span>
        </div>
      </div>
    );
  }

  if (c.type === "text") {
    return (
      <section className="rcard">
        <pre className="fv-text">{c.text}</pre>
      </section>
    );
  }

  return (
    <div className="empty-state">
      <span className="empty-ico">
        <Monitor size={24} strokeWidth={1.6} />
      </span>
      <h3>Preview not available</h3>
      <p>{c.note}</p>
    </div>
  );
}
