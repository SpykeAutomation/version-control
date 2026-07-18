// The repository Settings tab: access control (member list + add-member
// search) on top, and the danger zone at the bottom — visibility (locked to
// private), default branch, per-branch protection, ownership transfer, and
// repository deletion. Every
// danger-zone action explains its consequences in a confirm dialog first;
// nothing deploys on a single click.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Globe,
  Lock,
  Search,
  ShieldCheck,
  TriangleAlert,
  UserPlus,
  X,
} from "lucide-react";
import { ApiError } from "../api/client";
import type { Member, ProjectRow } from "../api/projects";
import type { BranchSummary } from "../api/commits";
import {
  errorText,
  useAddMember,
  useBranches,
  useDeleteProject,
  useMemberCandidates,
  useMembers,
  useRemoveMember,
  useSetBranchProtection,
  useSetDefaultBranch,
  useSetProjectIcon,
  useTransferOwnership,
  useUpdateMemberRole,
} from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { initials } from "../lib/initials";
import { REPO_ICONS, resolveRepoIcon } from "../lib/repoIcons";

// Every confirmable action the tab can stage. The dialog renders from this and
// nothing mutates until its Confirm button is pressed.
type PendingAction =
  | { kind: "protect"; branch: BranchSummary }
  | { kind: "unprotect"; branch: BranchSummary }
  | { kind: "set-default"; branch: BranchSummary; current: string }
  | { kind: "remove-member"; member: Member }
  | { kind: "transfer"; member: Member }
  | { kind: "delete-repo" };

export function RepositorySettings({ project }: { project: ProjectRow }) {
  const { user } = useAuth();
  const role = project.your_role ?? "member";
  const isOwner = role === "owner";
  const canManage = isOwner || role === "admin";

  const membersQ = useMembers(project.id);
  const branchesQ = useBranches(project.id);
  const [pending, setPending] = useState<PendingAction | null>(null);

  return (
    <div className="settings-col">
      {!canManage && (
        <div className="panel-msg">
          You have read-only access to these settings. Only repository owners
          and admins can change them.
        </div>
      )}

      <AccessSection
        project={project}
        members={membersQ.data ?? null}
        loading={membersQ.isPending}
        error={membersQ.error}
        canManage={canManage}
        isOwner={isOwner}
        meId={user?.id}
        onStage={setPending}
      />

      <AppearanceSection project={project} canManage={canManage} />

      <DangerZone
        branches={branchesQ.data ?? null}
        members={membersQ.data ?? null}
        canManage={canManage}
        isOwner={isOwner}
        meId={user?.id}
        onStage={setPending}
      />

      {pending && (
        <ConfirmActionModal
          project={project}
          action={pending}
          onClose={() => setPending(null)}
        />
      )}
    </div>
  );
}

// ---- Access control ----
function AccessSection({
  project,
  members,
  loading,
  error,
  canManage,
  isOwner,
  meId,
  onStage,
}: {
  project: ProjectRow;
  members: Member[] | null;
  loading: boolean;
  error: unknown;
  canManage: boolean;
  isOwner: boolean;
  meId?: number;
  onStage: (a: PendingAction) => void;
}) {
  const changeRole = useUpdateMemberRole(project.id);

  return (
    <section className="mr-section settings-section">
      <div className="mr-section-head">
        <div className="mr-section-title">
          Access
          <span className="mr-section-count">
            {members ? `${members.length} ${members.length === 1 ? "member" : "members"}` : "…"}
          </span>
        </div>
      </div>
      <div className="settings-body">
        <p className="settings-note">
          Access is granted per repository, not per organization. Members can
          view and commit; admins can also manage members and branch
          protection; the owner can additionally transfer or delete the
          repository.
        </p>

        {canManage && <AddMemberSearch project={project} members={members} />}

        {loading ? (
          <div className="rcard-empty">Loading members…</div>
        ) : error ? (
          <div className="rcard-empty">
            {errorText(error, "Couldn't load the member list.")}
          </div>
        ) : (
          <div className="dtable-scroll">
            <table className="dtable members-table">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {(members ?? []).map((m) => {
                  const isSelf = meId != null && m.id === meId;
                  const roleLocked =
                    !canManage ||
                    m.role === "owner" ||
                    isSelf ||
                    // Only the owner may touch an admin's role or membership.
                    (m.role === "admin" && !isOwner);
                  return (
                    <tr key={m.id}>
                      <td className="cell-strong">
                        <span className="author">
                          <span className="author-av">{initials(m.name)}</span>
                          {m.name}
                          {isSelf && <span className="settings-you">you</span>}
                        </span>
                      </td>
                      <td className="muted-cell">{m.email}</td>
                      <td>
                        {roleLocked ? (
                          <span className="badge gray">{m.role}</span>
                        ) : (
                          <select
                            className="select role-select"
                            value={m.role}
                            disabled={changeRole.isPending}
                            onChange={(e) => {
                              const next = e.target.value;
                              if (next === "owner") {
                                // Owner is not a role you set — it's an
                                // ownership transfer, staged like the other
                                // dangerous actions.
                                onStage({ kind: "transfer", member: m });
                                e.target.value = m.role;
                                return;
                              }
                              changeRole.mutate({
                                userId: m.id,
                                role: next as "member" | "admin",
                              });
                            }}
                          >
                            <option value="member">member</option>
                            <option value="admin">admin</option>
                            {isOwner && <option value="owner">owner…</option>}
                          </select>
                        )}
                      </td>
                      <td className="member-remove-cell">
                        {!roleLocked && (
                          <button
                            type="button"
                            className="file-remove"
                            aria-label={`Remove ${m.name}`}
                            title="Remove from repository"
                            onClick={() => onStage({ kind: "remove-member", member: m })}
                          >
                            <X size={15} strokeWidth={2} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {changeRole.error != null && (
          <div className="form-error">
            {errorText(changeRole.error, "Couldn't change the role.")}
          </div>
        )}
      </div>
    </section>
  );
}

// The add-member field: live search against the backend's candidate endpoint.
// Until that endpoint is deployed it 404s — then the field degrades to
// exact-email add through the existing members endpoint.
function AddMemberSearch({
  project,
  members,
}: {
  project: ProjectRow;
  members: Member[] | null;
}) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q), 250);
    return () => window.clearTimeout(t);
  }, [q]);

  const candidates = useMemberCandidates(project.id, debounced);
  const add = useAddMember(project.id);
  const searchUnavailable =
    candidates.error instanceof ApiError && candidates.error.status === 404;
  const emailish = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(q.trim());
  const memberEmails = new Set((members ?? []).map((m) => m.email));

  const addByEmail = (email: string) => {
    add.mutate(
      { email, role: "member" },
      { onSuccess: () => setQ("") },
    );
  };

  return (
    <div className="member-search">
      <div className="member-search-row">
        <span className="member-search-ico">
          <Search size={15} strokeWidth={1.9} />
        </span>
        <input
          className="input member-search-input"
          placeholder="Add people by name or email…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {searchUnavailable && emailish && (
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={add.isPending || memberEmails.has(q.trim())}
            onClick={() => addByEmail(q.trim())}
          >
            <UserPlus size={15} strokeWidth={1.9} />
            {add.isPending ? "Adding…" : "Add"}
          </button>
        )}
      </div>

      {searchUnavailable ? (
        <p className="settings-hint">
          Live search needs a backend update that isn't deployed yet — enter an
          exact email address and press Add. New members start with the
          <strong> member</strong> role.
        </p>
      ) : candidates.isFetching ? (
        <div className="ms-results">
          <div className="ms-empty">Searching…</div>
        </div>
      ) : candidates.data && debounced.trim().length >= 2 ? (
        <div className="ms-results">
          {candidates.data.length === 0 ? (
            <div className="ms-empty">
              No matching people in your organization.
            </div>
          ) : (
            candidates.data
              .filter((c) => !memberEmails.has(c.email))
              .map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="ms-row"
                  disabled={add.isPending}
                  onClick={() => addByEmail(c.email)}
                >
                  <span className="author-av">{initials(c.name)}</span>
                  <span className="ms-name">{c.name}</span>
                  <span className="ms-email">{c.email}</span>
                  <span className="ms-add">
                    <UserPlus size={14} strokeWidth={1.9} />
                    Add as member
                  </span>
                </button>
              ))
          )}
        </div>
      ) : null}

      {add.error != null && (
        <div className="form-error">
          {errorText(add.error, "Couldn't add that person.")}
        </div>
      )}
    </div>
  );
}

// ---- Appearance ----
// The repository icon: eight fixed glyph+tone pairs (lib/repoIcons), applied
// on click by owners and admins. Until the backend carries the icon field the
// mutation's echo-guard reports "not deployed yet" instead of a false success.
function AppearanceSection({
  project,
  canManage,
}: {
  project: ProjectRow;
  canManage: boolean;
}) {
  const setIcon = useSetProjectIcon(project.id);
  const current = resolveRepoIcon(project.icon, project.slug);
  return (
    <section className="mr-section settings-section">
      <div className="mr-section-head">
        <div className="mr-section-title">Appearance</div>
      </div>
      <div className="settings-body">
        <p className="settings-note">
          The icon this repository wears in lists and headers.
        </p>
        <div className="icon-pick">
          {REPO_ICONS.map((def) => (
            <button
              key={def.id}
              type="button"
              className={`icon-swatch tone-${def.tone}${current.id === def.id ? " selected" : ""}`}
              disabled={!canManage || setIcon.isPending}
              title={def.label}
              onClick={() => setIcon.mutate(def.id)}
            >
              {def.glyph(20)}
            </button>
          ))}
        </div>
        {setIcon.error != null && (
          <div className="form-error">
            {errorText(setIcon.error, "Couldn't change the icon.")}
          </div>
        )}
        {!canManage && (
          <p className="settings-hint">
            Only owners and admins can change the icon.
          </p>
        )}
      </div>
    </section>
  );
}

// ---- Danger zone ----
function DangerZone({
  branches,
  members,
  canManage,
  isOwner,
  meId,
  onStage,
}: {
  branches: BranchSummary[] | null;
  members: Member[] | null;
  canManage: boolean;
  isOwner: boolean;
  meId?: number;
  onStage: (a: PendingAction) => void;
}) {
  const defaultBranch = branches?.find((b) => b.isDefault)?.name ?? "main";
  // Candidates for a new default: any other branch that has commits.
  const defaultCandidates = (branches ?? []).filter(
    (b) => !b.isDefault && b.lastCommitSha != null,
  );
  const [defaultPick, setDefaultPick] = useState("");
  const others = (members ?? []).filter(
    (m) => m.role !== "owner" && m.id !== meId,
  );
  const [transferTo, setTransferTo] = useState<number | "">("");

  return (
    <section className="rcard danger-zone">
      <div className="dz-head">
        <TriangleAlert size={16} strokeWidth={2} />
        Danger zone
      </div>

      {/* Visibility — locked to private in this deployment. */}
      <div className="dz-row">
        <div className="dz-info">
          <div className="dz-title">Visibility</div>
          <p className="dz-desc">
            Who can see this repository. Every repository is visible to its
            members only — public repositories aren't available in this
            deployment.
          </p>
        </div>
        <div className="dz-action">
          <div className="seg dz-seg" role="radiogroup" aria-label="Visibility">
            <button type="button" className="seg-btn active" disabled>
              <Lock size={13} strokeWidth={2} />
              Private
            </button>
            <button
              type="button"
              className="seg-btn"
              disabled
              title="Public repositories aren't available in this deployment."
            >
              <Globe size={13} strokeWidth={2} />
              Public
            </button>
          </div>
        </div>
      </div>

      {/* Default branch — read-only until the backend can change it. */}
      <div className="dz-row">
        <div className="dz-info">
          <div className="dz-title">Default branch</div>
          <p className="dz-desc">
            The branch merge requests target by default and new branches start
            from. Currently <span className="branch-name">{defaultBranch}</span>.
          </p>
        </div>
        <div className="dz-action">
          {isOwner ? (
            <>
              <select
                className="select"
                value={defaultPick}
                onChange={(e) => setDefaultPick(e.target.value)}
              >
                <option value="">Choose a branch…</option>
                {defaultCandidates.map((b) => (
                  <option key={b.name} value={b.name}>
                    {b.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn-dz"
                disabled={defaultPick === ""}
                onClick={() => {
                  const branch = defaultCandidates.find(
                    (b) => b.name === defaultPick,
                  );
                  if (branch)
                    onStage({
                      kind: "set-default",
                      branch,
                      current: defaultBranch,
                    });
                }}
              >
                Change…
              </button>
            </>
          ) : (
            <span className="dz-locked">Only the owner can change this.</span>
          )}
        </div>
      </div>

      {/* Branch protection — per branch, staged behind a confirm. */}
      <div className="dz-row dz-row-branches">
        <div className="dz-info">
          <div className="dz-title">Branch protection</div>
          <p className="dz-desc">
            A protected branch rejects direct commits; changes land only
            through merge requests, which can require approvals before merging.
          </p>
        </div>
        <div className="dz-branches">
          {branches == null ? (
            <div className="rcard-empty">Loading branches…</div>
          ) : (
            branches.map((b) => (
              <div className="dz-branch" key={b.name}>
                <span className="branch-name">{b.name}</span>
                {b.isDefault && <span className="badge blue">default</span>}
                {b.isProtected ? (
                  <span className="badge green">
                    <ShieldCheck size={12} strokeWidth={2} />
                    protected
                    {b.requiredApprovals > 0 &&
                      ` · ${b.requiredApprovals} ${b.requiredApprovals === 1 ? "approval" : "approvals"}`}
                  </span>
                ) : (
                  <span className="badge gray">unprotected</span>
                )}
                <span className="dz-branch-spacer" />
                {canManage &&
                  (b.isProtected ? (
                    <button
                      type="button"
                      className="btn-dz"
                      disabled={b.isDefault}
                      title={
                        b.isDefault
                          ? "The default branch cannot be unprotected."
                          : undefined
                      }
                      onClick={() => onStage({ kind: "unprotect", branch: b })}
                    >
                      Unprotect…
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn-dz"
                      onClick={() => onStage({ kind: "protect", branch: b })}
                    >
                      Protect…
                    </button>
                  ))}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Ownership transfer — owner only. */}
      <div className="dz-row">
        <div className="dz-info">
          <div className="dz-title">Transfer ownership</div>
          <p className="dz-desc">
            Make another member the owner. You become an admin and cannot undo
            this yourself.
          </p>
        </div>
        <div className="dz-action">
          {isOwner ? (
            <>
              <select
                className="select"
                value={transferTo}
                onChange={(e) =>
                  setTransferTo(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">Choose a member…</option>
                {others.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.role})
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn-dz"
                disabled={transferTo === ""}
                onClick={() => {
                  const member = others.find((m) => m.id === transferTo);
                  if (member) onStage({ kind: "transfer", member });
                }}
              >
                Transfer…
              </button>
            </>
          ) : (
            <span className="dz-locked">Only the owner can transfer.</span>
          )}
        </div>
      </div>

      {/* Delete repository. */}
      <div className="dz-row">
        <div className="dz-info">
          <div className="dz-title">Delete this repository</div>
          <p className="dz-desc">
            Permanently deletes the repository: all branches, commits, merge
            requests, comments and member access. This cannot be undone.
          </p>
        </div>
        <div className="dz-action">
          {canManage ? (
            <button
              type="button"
              className="btn-dz"
              onClick={() => onStage({ kind: "delete-repo" })}
            >
              Delete repository…
            </button>
          ) : (
            <span className="dz-locked">Owners and admins only.</span>
          )}
        </div>
      </div>
    </section>
  );
}

// ---- The confirm dialog ----
// One modal for every staged action: it spells out exactly what will happen,
// and only its Confirm button runs the mutation.
function ConfirmActionModal({
  project,
  action,
  onClose,
}: {
  project: ProjectRow;
  action: PendingAction;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const protect = useSetBranchProtection(project.id);
  const setDefault = useSetDefaultBranch(project.id);
  const removeMember = useRemoveMember(project.id);
  const transfer = useTransferOwnership(project.id);
  const deleteRepo = useDeleteProject(project.id);

  // Protection dialog state: how many approvals a merge into the branch needs.
  const [approvals, setApprovals] = useState(1);
  // Delete dialog gate: the repository name must be typed back exactly.
  const [nameCheck, setNameCheck] = useState("");

  const busy =
    protect.isPending ||
    setDefault.isPending ||
    removeMember.isPending ||
    transfer.isPending ||
    deleteRepo.isPending;
  const error =
    protect.error ??
    setDefault.error ??
    removeMember.error ??
    transfer.error ??
    deleteRepo.error;

  const done = () => onClose();

  let title = "";
  let body: React.ReactNode = null;
  let confirmLabel = "Confirm";
  let confirmDisabled = false;
  let onConfirm = () => {};

  switch (action.kind) {
    case "protect":
      title = `Protect ${action.branch.name}`;
      confirmLabel = "Protect branch";
      body = (
        <>
          <p>
            Protecting <span className="branch-name">{action.branch.name}</span>{" "}
            means:
          </p>
          <ul className="dz-consequences">
            <li>Direct commits to this branch will be rejected.</li>
            <li>Changes can only land through merge requests.</li>
            <li>The branch cannot be deleted while protected.</li>
          </ul>
          <label className="dz-approvals">
            Required approvals to merge
            <input
              className="input dz-approvals-input"
              type="number"
              min={0}
              max={10}
              value={approvals}
              onChange={(e) =>
                setApprovals(Math.max(0, Math.min(10, Number(e.target.value) || 0)))
              }
            />
          </label>
          <p className="dz-fine">
            0 means merge requests need no approvals but direct commits stay
            blocked.
          </p>
        </>
      );
      onConfirm = () =>
        protect.mutate(
          {
            branch: action.branch.name,
            isProtected: true,
            requiredApprovals: approvals,
          },
          { onSuccess: done },
        );
      break;

    case "unprotect":
      title = `Unprotect ${action.branch.name}`;
      confirmLabel = "Remove protection";
      body = (
        <>
          <p>
            Removing protection from{" "}
            <span className="branch-name">{action.branch.name}</span> means:
          </p>
          <ul className="dz-consequences">
            <li>Anyone with access can commit to it directly.</li>
            <li>Merge requests into it will no longer require approvals.</li>
            <li>The branch becomes deletable.</li>
          </ul>
        </>
      );
      onConfirm = () =>
        protect.mutate(
          { branch: action.branch.name, isProtected: false, requiredApprovals: 0 },
          { onSuccess: done },
        );
      break;

    case "set-default":
      title = `Make ${action.branch.name} the default branch`;
      confirmLabel = "Change default branch";
      body = (
        <>
          <p>
            Making <span className="branch-name">{action.branch.name}</span>{" "}
            the default (currently{" "}
            <span className="branch-name">{action.current}</span>) means:
          </p>
          <ul className="dz-consequences">
            <li>Merge requests will target it by default.</li>
            <li>New branches will start from it.</li>
            <li>
              It becomes the protected default: it can't be deleted and its
              protection can't be removed.
            </li>
            <li>
              <span className="branch-name">{action.current}</span> keeps any
              explicit protection but loses its default status.
            </li>
          </ul>
        </>
      );
      onConfirm = () => setDefault.mutate(action.branch.name, { onSuccess: done });
      break;

    case "remove-member":
      title = `Remove ${action.member.name}`;
      confirmLabel = "Remove member";
      body = (
        <p>
          {action.member.name} ({action.member.email}) will immediately lose
          access to this repository — they can no longer view it, commit, or
          comment. Their past commits and comments remain in the history. They
          can be re-added later.
        </p>
      );
      onConfirm = () =>
        removeMember.mutate(action.member.id, { onSuccess: done });
      break;

    case "transfer":
      title = `Transfer ownership to ${action.member.name}`;
      confirmLabel = "Transfer ownership";
      body = (
        <>
          <p>
            {action.member.name} ({action.member.email}) becomes the{" "}
            <strong>owner</strong> of {project.name}. This means:
          </p>
          <ul className="dz-consequences">
            <li>You are demoted to admin.</li>
            <li>
              Only the new owner can transfer ownership back, change admins'
              roles, or remove admins.
            </li>
            <li>This takes effect immediately and you cannot undo it.</li>
          </ul>
        </>
      );
      onConfirm = () => transfer.mutate(action.member.id, { onSuccess: done });
      break;

    case "delete-repo":
      title = `Delete ${project.name}`;
      confirmLabel = "Delete this repository";
      confirmDisabled = nameCheck !== project.name;
      body = (
        <>
          <p>
            This permanently deletes <strong>{project.name}</strong> — every
            branch, commit, merge request, comment, and member association.
            There is no undo and no recovery.
          </p>
          <label className="dz-approvals">
            <span className="dz-confirm-phrase">
              Type <strong>{project.name}</strong> to confirm
            </span>
            <input
              className="input"
              value={nameCheck}
              onChange={(e) => setNameCheck(e.target.value)}
              placeholder={project.name}
              autoFocus
            />
          </label>
        </>
      );
      onConfirm = () =>
        deleteRepo.mutate(undefined, {
          onSuccess: () => navigate("/organization"),
        });
      break;
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal dz-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="modal-title">
          <TriangleAlert size={17} strokeWidth={2} className="dz-modal-ico" />
          {title}
        </h3>
        <div className="dz-modal-body">{body}</div>
        {error != null && (
          <div className="form-error">
            {errorText(error, "The change was not applied.")}
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-dz-confirm"
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
          >
            {busy ? "Applying…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
