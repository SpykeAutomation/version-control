import { Link, useParams } from "react-router-dom";
import { ChevronDown, GitBranch } from "lucide-react";
import { ProtectedLock } from "../components/ProtectedLock";
import { useAuth } from "../auth/AuthContext";
import { errorText, useBranches, useProject } from "../api/queries";
import { timeAgo } from "../lib/time";

// All of a repository's branches in one table. Rows link to the branch's tree
// view; the tip commit links to its review page.
export function BranchesPage() {
  const { slug } = useParams();
  const { user } = useAuth();
  const { project, isPending, error } = useProject(slug);
  const branchesQuery = useBranches(project?.id);
  const branches = branchesQuery.data ?? null;

  return (
    <div className="app-scroll">
      {error ? (
        <div className="page-pad">
          <div className="panel-msg error">
            {errorText(error, "Failed to load branches.")}
          </div>
        </div>
      ) : isPending || !project ? (
        <div className="page-pad">
          <div className="panel-msg">Loading branches…</div>
        </div>
      ) : (
        <div className="mr-page">
          <nav className="crumb">
            <Link to="/organization">{user?.organization ?? "Repositories"}</Link>
            <span className="crumb-sep">/</span>
            <Link to={`/organization/${slug}`}>{project.name}</Link>
            <span className="crumb-sep">/</span>
            <span>Branches</span>
          </nav>

          <header className="mr-head">
            <div className="mr-head-main">
              <div className="mr-title-row">
                <h1 className="mr-title">Branches</h1>
              </div>
              <p className="mr-sub">
                Every branch in {project.name}, with its tip commit and how far
                it has diverged from the default branch.
              </p>
            </div>
          </header>

          <div className="rcard">
            {!branches ? (
              <div className="rcard-empty">Loading branches…</div>
            ) : branches.length === 0 ? (
              <div className="rcard-empty">No branches yet.</div>
            ) : (
              <div className="dtable-scroll"><table className="dtable">
                <thead>
                  <tr>
                    <th>Branch</th>
                    <th>Latest commit</th>
                    <th>Latest activity</th>
                    <th>Ahead / Behind</th>
                  </tr>
                </thead>
                <tbody>
                  {branches.map((b) => (
                    <tr key={b.name}>
                      <td>
                        <Link
                          to={`/organization/${slug}?tab=Files&branch=${encodeURIComponent(b.name)}`}
                          className="branch-name crlink"
                        >
                          <GitBranch size={13} strokeWidth={2} />
                          {b.name}
                        </Link>
                        {b.isDefault && (
                          <span className="mini-badge" style={{ marginLeft: 8 }}>
                            Default
                          </span>
                        )}
                        {b.isProtected && (
                          <ProtectedLock style={{ marginLeft: 8 }} />
                        )}
                      </td>
                      <td>
                        {b.lastCommitHash ? (
                          <>
                            <Link
                              to={`/organization/${slug}/commit/${b.lastCommitSha}`}
                              className="hash crlink"
                            >
                              {b.lastCommitHash}
                            </Link>{" "}
                            <span className="branch-msg">
                              {b.lastCommitMessage}
                            </span>
                          </>
                        ) : (
                          <span className="muted-cell">No commits</span>
                        )}
                      </td>
                      <td className="muted-cell">
                        {b.lastCommitAt ? timeAgo(b.lastCommitAt) : "—"}
                      </td>
                      <td className="muted-cell">
                        {b.ahead === 0 && b.behind === 0 ? (
                          "–"
                        ) : (
                          <span className="branch-ab">
                            <span className="ab-behind">
                              <ChevronDown size={12} strokeWidth={2} />
                              {b.behind}
                            </span>
                            <span className="ab-ahead">
                              <ChevronDown
                                size={12}
                                strokeWidth={2}
                                style={{ transform: "rotate(180deg)" }}
                              />
                              {b.ahead}
                            </span>
                          </span>
                        )}
                      </td>
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
