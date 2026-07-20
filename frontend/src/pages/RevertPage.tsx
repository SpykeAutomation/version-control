// Revert preview: the confirmation step of the revert flow. Reached from the
// commit page's revert dialog with ?branch=&target=&tip= — it shows exactly
// what confirming will change (the diff base=current tip, head=target, which
// equals the diff of the revert commit-to-be against its parent) and a
// Confirm button that calls POST /revert. The backend re-checks the tip
// inside its write lock; a 409 here means the branch moved mid-preview.
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  GitBranch,
  GitCommitHorizontal,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import { RoutineLadderDiffView } from "../components/LadderDiff";
import { revertBranch } from "../api/commits";
import { ApiError } from "../api/client";
import {
  errorText,
  useCommits,
  useCompareView,
  useLadderDiff,
  useProject,
} from "../api/queries";
import { formatDate, timeAgo } from "../lib/time";
import { shortSha } from "../lib/format";

export function RevertPage() {
  const { slug } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const branch = params.get("branch") ?? "";
  const target = params.get("target") ?? "";
  const tip = params.get("tip") ?? "";

  const { project, isPending, error: loadErr } = useProject(slug);
  const projectId = project?.id;
  const commits = useCommits(projectId, branch).data ?? null;
  const compare = useCompareView(projectId, tip, target);
  const ladder = useLadderDiff(projectId, tip, target);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ status?: number; message: string } | null>(
    null,
  );

  if (loadErr || (!isPending && !project)) {
    return (
      <div className="app-scroll">
        <div className="page-pad">
          <div className="panel-msg error">
            {loadErr ? errorText(loadErr, "Failed to load project.") : "Repository not found."}
          </div>
        </div>
      </div>
    );
  }
  if (isPending || !project) {
    return (
      <div className="app-scroll">
        <div className="page-pad">
          <div className="panel-msg">Loading…</div>
        </div>
      </div>
    );
  }
  if (!branch || !target || !tip) {
    return (
      <div className="app-scroll">
        <div className="page-pad">
          <div className="panel-msg error">
            This revert preview is missing its parameters. Start again from the
            commit page's Revert button.
          </div>
        </div>
      </div>
    );
  }

  const targetMeta = commits?.find((c) => c.sha === target) ?? null;
  // How many commits sit above the target on this branch — that's what the
  // revert undoes. (The compare summary's `commits` counts base→head, which
  // is 0 when head is an ancestor of base, so it can't be used here.)
  const targetIdx = commits?.findIndex((c) => c.sha === target) ?? -1;
  // The preview was computed against `tip`; if the branch has already moved,
  // confirming would 409 anyway — surface it before the user reads the diff.
  const branchMoved = commits != null && commits[0]?.sha !== tip;

  async function confirm() {
    if (!projectId || submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      const res = await revertBranch(projectId, {
        branch,
        targetSha: target,
        expectedTipSha: tip,
      });
      // The branch tip, commit list and activity all just changed.
      qc.invalidateQueries({ queryKey: ["projects", projectId] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/organization/${slug}/commit/${res.sha}`);
    } catch (e) {
      setError({
        status: e instanceof ApiError ? e.status : undefined,
        message:
          e instanceof ApiError ? e.message : "Couldn't revert. Try again.",
      });
      setSubmitting(false);
    }
  }

  const s = compare.data?.summary;

  return (
    <div className="app-scroll">
      <div className="mr-page revert-page">
        <nav className="crumb">
          <Link to="/organization">Repositories</Link>
          <span className="crumb-sep">/</span>
          <Link to={`/organization/${slug}`}>{project.name}</Link>
          <span className="crumb-sep">/</span>
          <span>Revert</span>
        </nav>

        <header className="mr-head">
          <span className="mr-glyph cm-glyph" aria-hidden="true">
            <RotateCcw size={22} strokeWidth={1.8} />
          </span>
          <div className="mr-head-main">
            <div className="mr-title-row">
              <h1 className="mr-title">
                Revert{" "}
                <span className="branch-tag">
                  <GitBranch size={13} strokeWidth={2} />
                  {branch}
                </span>{" "}
                to <span className="cm-commit-sha">{shortSha(target)}</span>
              </h1>
            </div>
            <p className="mr-sub">
              {targetMeta ? (
                <>
                  “{targetMeta.message}” — {targetMeta.author},{" "}
                  {timeAgo(targetMeta.at)} ({formatDate(targetMeta.at)})
                </>
              ) : (
                <>Restoring the repository state of commit {shortSha(target)}.</>
              )}
            </p>
          </div>
        </header>

        <div className="revert-warn">
          <TriangleAlert size={16} strokeWidth={2} />
          <div>
            Confirming adds <strong>one new commit</strong> to{" "}
            <strong>{branch}</strong> that restores the repository to the state
            of <strong>{shortSha(target)}</strong>. Nothing is deleted — every
            commit in between stays in the history, and this revert can itself
            be reverted. The changes below are exactly what the new commit will
            apply.
          </div>
        </div>

        {branchMoved && (
          <div className="form-error commit-error">
            The branch has moved since this preview was opened — someone
            committed to {branch} in the meantime. Go back to{" "}
            <Link to={`/organization/${slug}?tab=commits`}>the commit list</Link>{" "}
            and start the revert from the new latest commit.
          </div>
        )}
        {error && (
          <div className="form-error commit-error">
            {error.status === 409 ? (
              <>
                The branch moved while you were previewing ({error.message}).
                Go back to{" "}
                <Link to={`/organization/${slug}?tab=commits`}>the commit list</Link>{" "}
                and start over from the new latest commit.
              </>
            ) : (
              error.message
            )}
          </div>
        )}

        {compare.isPending ? (
          <div className="panel-msg">Computing the changes this revert will apply…</div>
        ) : compare.error ? (
          <div className="panel-msg error">
            {errorText(compare.error, "Couldn't compute the revert preview.")}
          </div>
        ) : s ? (
          <>
            <div className="revert-summary">
              <SummaryStat label="Files changed" value={s.files_changed} />
              <SummaryStat
                label="Rungs"
                value={s.rungs_added + s.rungs_removed + s.rungs_modified}
                sub={
                  <>
                    <span className="t-add">+{s.rungs_added}</span>{" "}
                    <span className="t-rem">−{s.rungs_removed}</span>{" "}
                    <span className="t-mod">~{s.rungs_modified}</span>
                  </>
                }
              />
              <SummaryStat label="Routines modified" value={s.routines_modified} />
              <SummaryStat label="Tags impacted" value={s.tags_impacted} />
              {targetIdx > 0 && (
                <SummaryStat
                  label="Commits being reverted"
                  value={targetIdx}
                  sub={<>between {shortSha(target)} and the tip</>}
                />
              )}
            </div>

            {compare.data!.files.length > 0 && (
              <section className="rcard revert-files">
                <div className="rcard-head">
                  <span className="rcard-title">
                    Files this revert touches ({compare.data!.files.length})
                  </span>
                </div>
                <div className="dtable-scroll">
                  <table className="dtable l5x-table">
                    <thead>
                      <tr>
                        <th>File</th>
                        <th>Change</th>
                        <th>Rungs</th>
                        <th>Symbols</th>
                      </tr>
                    </thead>
                    <tbody>
                      {compare.data!.files.map((f) => (
                        <tr key={f.path}>
                          <td className="cell-strong">{f.path}</td>
                          <td className="muted-cell">{f.change}</td>
                          <td className="muted-cell">
                            <span className="t-add">+{f.rungs_added}</span>{" "}
                            <span className="t-rem">−{f.rungs_removed}</span>{" "}
                            <span className="t-mod">~{f.rungs_modified}</span>
                          </td>
                          <td className="muted-cell">
                            {f.symbols.slice(0, 6).join(", ")}
                            {f.symbols.length > 6 && ` +${f.symbols.length - 6} more`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {ladder.isPending ? (
              <div className="panel-msg">Loading the ladder detail…</div>
            ) : (ladder.data?.routines.length ?? 0) > 0 ? (
              <section className="revert-ladder">
                {ladder.data!.routines.map((r, i) => (
                  <div className="revert-routine" key={i}>
                    <div className="revert-routine-head">
                      <GitCommitHorizontal size={14} strokeWidth={1.8} />
                      <span className="revert-routine-name">
                        {[r.program, r.routine].filter(Boolean).join(" / ") ||
                          "Routine"}
                      </span>
                    </div>
                    <div className="mr-ladderwrap">
                      <RoutineLadderDiffView routine={r} showNumbers />
                    </div>
                  </div>
                ))}
              </section>
            ) : null}
          </>
        ) : null}

        <div className="revert-footer">
          <Link
            to={`/organization/${slug}/commit/${tip}`}
            className="btn btn-quiet"
          >
            Cancel
          </Link>
          <button
            type="button"
            className="btn btn-revert"
            disabled={submitting || branchMoved || compare.isPending || !!compare.error}
            onClick={confirm}
          >
            <RotateCcw size={15} strokeWidth={1.9} />
            {submitting ? "Reverting…" : `Confirm revert of ${branch}`}
          </button>
        </div>
      </div>
    </div>
  );
}

function SummaryStat({
  label,
  value,
  sub,
}: {
  label: string;
  value: number;
  sub?: React.ReactNode;
}) {
  return (
    <div className="revert-stat">
      <div className="revert-stat-num">{value}</div>
      <div className="revert-stat-label">{label}</div>
      {sub && <div className="revert-stat-sub">{sub}</div>}
    </div>
  );
}
