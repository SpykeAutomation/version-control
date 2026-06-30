import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Box,
  ChevronDown,
  FileCode2,
  GitBranch,
  GitCommitHorizontal,
  GitCompare,
  GitPullRequestArrow,
  Layers,
  MessageSquare,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";
import { commitFiles, createBranch } from "../api/commits";
import { createChangeRequest } from "../api/mergeRequest";
import { ApiError } from "../api/client";
import { errorText, queryKeys, useProject } from "../api/queries";

// L5X is the PLC export the engine reads; anything else rides along as a
// supporting file and is shown neutrally.
function fileType(name: string): { ext: string; tone: string } {
  const ext = name.includes(".") ? name.split(".").pop()!.toUpperCase() : "FILE";
  return { ext, tone: ext === "L5X" ? "blue" : "gray" };
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const ACCEPT = ".L5X,.l5x";

export function CommitPage() {
  const { slug: routeSlug } = useParams();
  const navigate = useNavigate();

  const { project, isPending, error: loadErr } = useProject(routeSlug);
  const slug = routeSlug;
  const loadError = loadErr ? errorText(loadErr, "Failed to load project.") : null;
  const qc = useQueryClient();

  const [files, setFiles] = useState<File[]>([]);
  const [branch, setBranch] = useState("");
  const [newBranch, setNewBranch] = useState("");
  const [message, setMessage] = useState("");
  const [description, setDescription] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState<"commit" | "request" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Default the branch to the project's first branch once it loads.
  useEffect(() => {
    if (project && !branch) setBranch(project.branches[0] ?? "main");
  }, [project, branch]);

  function addFiles(incoming: FileList | File[]) {
    const next = [...files];
    for (const f of Array.from(incoming)) {
      if (!next.some((e) => e.name === f.name && e.size === f.size)) next.push(f);
    }
    setFiles(next);
  }
  function removeFile(idx: number) {
    setFiles(files.filter((_, i) => i !== idx));
  }

  // The branch this commit lands on. When "+ Create new branch…" is selected,
  // it's the typed name; otherwise it's the chosen existing branch.
  const targetBranch = branch === "__new__" ? newBranch.trim() : branch;
  const totalSize = files.reduce((s, f) => s + f.size, 0);
  const canCommit =
    files.length > 0 &&
    message.trim().length > 0 &&
    !submitting &&
    (branch !== "__new__" || newBranch.trim().length > 0);
  // Committing to main lands directly; committing to any other branch opens a
  // change request to merge it back into main after review. The action below
  // adapts to whichever branch is selected.
  const isMain = targetBranch === "main";

  async function submit(kind: "commit" | "request") {
    if (!project || !canCommit) return;
    setError(null);
    setSubmitting(kind);
    try {
      if (branch === "__new__") {
        try {
          await createBranch(project.id, targetBranch, "main");
          // A new branch changes the project's branch list; refresh it.
          qc.invalidateQueries({ queryKey: queryKeys.projects });
        } catch (e) {
          // A branch that already exists is fine — fall through and commit to
          // it; surface anything else.
          const exists =
            e instanceof ApiError && /exist/i.test(e.message);
          if (!exists) throw e;
        }
      }
      await commitFiles(project.id, {
        branch: targetBranch,
        message: message.trim(),
        description: description.trim(),
        files,
      });
      // The commit (and any change request) just changed this project's data;
      // drop the cached queries so the next page shows the new state.
      qc.invalidateQueries({ queryKey: ["projects", project.id] });
      qc.invalidateQueries({ queryKey: queryKeys.projects });
      if (kind === "request") {
        const pr = await createChangeRequest(project.id, {
          title: message.trim(),
          description: description.trim(),
          sourceBranch: targetBranch,
          targetBranch: "main",
        });
        navigate(`/projects/${slug}/merge/${pr.number}`);
      } else {
        navigate(`/projects/${slug}`);
      }
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Couldn't commit the files. Try again.",
      );
      setSubmitting(null);
    }
  }

  return (
      <div className="app-scroll">
        {loadError ? (
          <div className="page-pad">
            <div className="panel-msg error">{loadError}</div>
          </div>
        ) : isPending ? (
          <div className="page-pad">
            <div className="panel-msg">Loading…</div>
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
          <div className="mr-page">
            <nav className="crumb">
              <Link to="/projects">Repositories</Link>
              <span className="crumb-sep">/</span>
              <Link to={`/projects/${project.slug}`}>{project.name}</Link>
              <span className="crumb-sep">/</span>
              <span>Commit</span>
            </nav>

            <header className="mr-head">
              <div className="mr-head-main">
                <div className="mr-title-row">
                  <h1 className="mr-title">Upload files and create commit</h1>
                </div>
                <p className="mr-sub">
                  Upload PLC files and commit them to the selected branch.
                </p>
              </div>
            </header>

            <div className="field commit-branch">
              <label className="label" htmlFor="commit-branch">
                Target branch
              </label>
              <div className="select-wrap">
                <GitBranch className="select-lead" size={15} strokeWidth={1.8} />
                <select
                  id="commit-branch"
                  className="select has-lead"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                >
                  {project.branches.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                  <option value="__new__">+ Create new branch…</option>
                </select>
                <ChevronDown className="select-caret" size={16} strokeWidth={1.8} />
              </div>
              {branch === "__new__" && (
                <input
                  className="input"
                  style={{ marginTop: 8 }}
                  placeholder="feature/my-change"
                  value={newBranch}
                  onChange={(e) => setNewBranch(e.target.value)}
                  aria-label="New branch name"
                />
              )}
            </div>

            {error && <div className="form-error commit-error">{error}</div>}

            <div className="commit-grid">
              <div className="commit-main">
                {/* Step 1 — upload */}
                <section className="rcard">
                  <StepHead n={1} title="Upload files" />
                  <div
                    className={`dropzone${dragOver ? " drag" : ""}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragOver(false);
                      addFiles(e.dataTransfer.files);
                    }}
                    onClick={() => inputRef.current?.click()}
                  >
                    <span className="dropzone-cloud">
                      <UploadCloud size={30} strokeWidth={1.7} />
                    </span>
                    <p className="dropzone-title">Drag and drop PLC files here</p>
                    <p className="dropzone-hint">Supports .L5X files</p>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        inputRef.current?.click();
                      }}
                    >
                      Browse files
                    </button>
                    <input
                      ref={inputRef}
                      type="file"
                      multiple
                      accept={ACCEPT}
                      hidden
                      onChange={(e) => {
                        if (e.target.files) addFiles(e.target.files);
                        e.target.value = "";
                      }}
                    />
                  </div>
                </section>

                {/* Step 2 — selected files */}
                <section className="rcard">
                  <StepHead
                    n={2}
                    title="Selected files"
                    count={files.length || undefined}
                  />
                  {files.length === 0 ? (
                    <div className="rcard-empty">No files selected yet.</div>
                  ) : (
                    <table className="dtable filelist">
                      <thead>
                        <tr>
                          <th>File name</th>
                          <th>Type</th>
                          <th>Size</th>
                          <th aria-label="Remove" />
                        </tr>
                      </thead>
                      <tbody>
                        {files.map((f, i) => {
                          const t = fileType(f.name);
                          return (
                            <tr key={`${f.name}-${f.size}`}>
                              <td className="cell-strong">
                                <span className="file-name">
                                  <FileCode2
                                    size={15}
                                    strokeWidth={1.7}
                                    className="file-ico"
                                  />
                                  {f.name}
                                </span>
                              </td>
                              <td>
                                <span className={`badge ${t.tone}`}>{t.ext}</span>
                              </td>
                              <td className="muted-cell">{formatSize(f.size)}</td>
                              <td className="file-remove-cell">
                                <button
                                  type="button"
                                  className="file-remove"
                                  aria-label={`Remove ${f.name}`}
                                  onClick={() => removeFile(i)}
                                >
                                  <X size={15} strokeWidth={2} />
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </section>
              </div>

              {/* Middle — commit details, summary, actions */}
              <div className="commit-mid">
                <section className="rcard">
                  <StepHead n={3} title="Commit details" />
                  <div className="rcard-body">
                    <div className="field">
                      <label className="label" htmlFor="commit-message">
                        Commit message <span className="req">*</span>
                      </label>
                      <input
                        id="commit-message"
                        className="input"
                        placeholder="Describe what changed"
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                      />
                    </div>
                    <div className="field" style={{ marginBottom: 0 }}>
                      <label className="label" htmlFor="commit-description">
                        Description <span className="label-weak">(optional)</span>
                      </label>
                      <textarea
                        id="commit-description"
                        className="textarea tall"
                        placeholder="Add any context for reviewers"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                      />
                    </div>
                  </div>
                </section>

                <section className="rcard">
                  <div className="rcard-head">
                    <span className="rcard-title">Change summary</span>
                  </div>
                  <div className="summary">
                    <SummaryRow
                      icon={<FileCode2 size={16} strokeWidth={1.7} />}
                      value={files.length}
                      label={files.length === 1 ? "file to add" : "files to add"}
                    />
                    <SummaryRow
                      icon={<Layers size={16} strokeWidth={1.7} />}
                      value={formatSize(totalSize)}
                      label="total size"
                    />
                  </div>
                </section>

                <div className="commit-actions">
                  <button
                    type="button"
                    className={`btn btn-block ${isMain ? "btn-primary" : "btn-approve"}`}
                    disabled={!canCommit}
                    onClick={() => submit(isMain ? "commit" : "request")}
                  >
                    {submitting
                      ? isMain
                        ? "Committing…"
                        : "Creating…"
                      : isMain
                        ? "Commit to main"
                        : "Commit and create change request"}
                  </button>
                  <p className="commit-actions-hint">
                    {isMain
                      ? "Commits directly to the main branch."
                      : `Commits to ${targetBranch || "the new branch"}, then opens a change request to merge into main.`}
                  </p>
                  <Link
                    to={`/projects/${project.slug}`}
                    className="btn btn-quiet btn-block"
                  >
                    Cancel
                  </Link>
                </div>
              </div>

              {/* Right — about / help */}
              <aside className="commit-rail">
                <section className="rcard">
                  <div className="rcard-head">
                    <span className="rcard-title">About uploading files</span>
                  </div>
                  <div className="about-body">
                    <p className="about-intro">
                      Spyke versions a PLC project the way source control
                      versions code. Every upload is a commit — a permanent,
                      comparable snapshot of your files on a branch.
                    </p>
                    <div className="about-item">
                      <span className="about-ico">
                        <GitCommitHorizontal size={16} strokeWidth={1.9} />
                      </span>
                      <div>
                        <div className="about-item-title">Commits keep history</div>
                        <div className="about-item-desc">
                          Each upload becomes a commit on the target branch.
                          Commits aren't overwritten, so the record of who
                          changed what, and when, stays intact — and you can go
                          back to any earlier version.
                        </div>
                      </div>
                    </div>
                    <div className="about-item">
                      <span className="about-ico">
                        <GitBranch size={16} strokeWidth={1.9} />
                      </span>
                      <div>
                        <div className="about-item-title">Branches isolate work</div>
                        <div className="about-item-desc">
                          A branch is a separate line of work. Develop and test
                          on a branch without affecting the version other people
                          are running on main.
                        </div>
                      </div>
                    </div>
                    <div className="about-item">
                      <span className="about-ico">
                        <ShieldCheck size={16} strokeWidth={1.9} />
                      </span>
                      <div>
                        <div className="about-item-title">Protected main</div>
                        <div className="about-item-desc">
                          main usually mirrors what's on the floor, so it's
                          protected: you can't commit to it directly. Upload to
                          another branch instead, then merge it back through
                          review — that keeps untested logic off the production
                          controller.
                        </div>
                      </div>
                    </div>
                    <div className="about-item">
                      <span className="about-ico">
                        <GitPullRequestArrow size={16} strokeWidth={1.9} />
                      </span>
                      <div>
                        <div className="about-item-title">
                          Change requests merge to main
                        </div>
                        <div className="about-item-desc">
                          To bring a branch into main, open a change request. It
                          stays open for discussion and review until a teammate
                          approves the merge.
                        </div>
                      </div>
                    </div>
                    <div className="about-item">
                      <span className="about-ico">
                        <GitCompare size={16} strokeWidth={1.9} />
                      </span>
                      <div>
                        <div className="about-item-title">Reviewers read the diff</div>
                        <div className="about-item-desc">
                          A change request shows a semantic diff — the rungs,
                          routines, and tags that actually changed, not raw XML —
                          so a reviewer can see exactly what moved before it
                          ships.
                        </div>
                      </div>
                    </div>
                    <div className="about-item">
                      <span className="about-ico">
                        <MessageSquare size={16} strokeWidth={1.9} />
                      </span>
                      <div>
                        <div className="about-item-title">Write a useful message</div>
                        <div className="about-item-desc">
                          Say what changed and why. Months later, the commit
                          message is what explains an adjusted timer or an added
                          interlock — group related files into one commit so each
                          version tells a complete story.
                        </div>
                      </div>
                    </div>
                  </div>
                </section>
              </aside>
            </div>
          </div>
        )}
      </div>
  );
}

function StepHead({ n, title, count }: { n: number; title: string; count?: number }) {
  return (
    <div className="step-head">
      <span className="step-num">{n}</span>
      <span className="step-title">{title}</span>
      {count !== undefined && <span className="step-count">{count}</span>}
    </div>
  );
}

function SummaryRow({
  icon,
  value,
  label,
}: {
  icon: ReactNode;
  value: number | string;
  label: string;
}) {
  return (
    <div className="summary-row">
      <span className="summary-ico">{icon}</span>
      <span className="summary-value">{value}</span>
      <span className="summary-label">{label}</span>
    </div>
  );
}
