import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Boxes,
  Braces,
  Download,
  FileCode2,
  FileSpreadsheet,
  FileText,
  GitBranch,
  Monitor,
  Tag,
} from "lucide-react";
import { TopBar } from "../app/TopBar";
import { RungView } from "../components/Ladder";
import { listProjects, type ProjectRow } from "../api/projects";
import { ApiError } from "../api/client";
import {
  FILE_KIND_LABEL,
  type FileEntry,
  type FileKind,
  type RepositoryDetail,
} from "../api/repository";
import { timeAgo } from "../lib/time";
import { TEMP_REPO_DETAIL } from "./__tempRepoData";

const FILE_ICON: Record<FileKind, typeof Tag> = {
  program: Boxes,
  routine: FileCode2,
  tags: Tag,
  io: FileSpreadsheet,
  hmi: Monitor,
  document: FileText,
  udt: Braces,
};

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function FileViewPage() {
  const { slug, fileName } = useParams();
  const name = fileName ? decodeURIComponent(fileName) : "";
  const [projects, setProjects] = useState<ProjectRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Failed to load file."),
      );
  }, []);

  const project = useMemo(
    () => projects?.find((p) => p.slug === slug) ?? null,
    [projects, slug],
  );

  // Preview data fills the page until the backend supplies it; `null` shows empty states.
  const detail: RepositoryDetail | null = TEMP_REPO_DETAIL;
  const file = useMemo(
    () => detail?.fileList.find((f) => f.name === name) ?? null,
    [detail, name],
  );

  const actions = file && (
    <button className="btn btn-outline btn-sm">
      <Download size={15} strokeWidth={1.8} />
      Download
    </button>
  );

  return (
    <>
      <TopBar actions={actions} />
      <div className="app-scroll">
        {error ? (
          <div className="page-pad">
            <div className="panel-msg error">{error}</div>
          </div>
        ) : !projects ? (
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
          <div className="repo-page">
            <nav className="crumb">
              <Link to="/projects">Projects</Link>
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
  const Icon = FILE_ICON[file.kind];
  return (
    <header className="fv-head">
      <span className="fv-head-ico">
        <Icon size={22} strokeWidth={1.9} />
      </span>
      <div className="fv-head-main">
        <h1 className="fv-name">{file.name}</h1>
        <div className="fv-meta">
          <span className="fv-kind">{FILE_KIND_LABEL[file.kind]}</span>
          <span className="fv-dot">·</span>
          <span>{file.size}</span>
          <span className="fv-dot">·</span>
          <span>Updated {timeAgo(file.modifiedAt)}</span>
          <span className="fv-dot">·</span>
          <span className="author">
            <span className="author-av">{initials(file.modifiedBy)}</span>
            {file.modifiedBy}
          </span>
        </div>
      </div>
    </header>
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
