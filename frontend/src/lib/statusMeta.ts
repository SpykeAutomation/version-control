// The one palette for change-request / merge-request status chips, so the
// repo page's list and the merge-request page can never drift apart.
export const STATUS_META: Record<
  "open" | "review" | "approved" | "changes" | "merged",
  { tone: string; label: string }
> = {
  open: { tone: "orange", label: "Open" },
  review: { tone: "blue", label: "In review" },
  approved: { tone: "green", label: "Approved" },
  changes: { tone: "red", label: "Changes requested" },
  merged: { tone: "purple", label: "Merged" },
};
