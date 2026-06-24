import type { RepoStatus } from "../api/projects";

// Maps a repository lifecycle status to a calm, color-coded badge. A dot sits
// next to the label so status never depends on color alone.
const MAP: Record<RepoStatus, { tone: string; label: string }> = {
  production: { tone: "green", label: "Production" },
  commissioning: { tone: "blue", label: "Commissioning" },
  review: { tone: "orange", label: "Review" },
  draft: { tone: "gray", label: "Draft" },
};

export function StatusBadge({ status }: { status: RepoStatus }) {
  const { tone, label } = MAP[status];
  return (
    <span className={`badge ${tone}`}>
      <span className="badge-dot" aria-hidden="true" />
      {label}
    </span>
  );
}
