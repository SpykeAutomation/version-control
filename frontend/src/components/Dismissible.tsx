// Wraps a card the user can close forever with the × in its corner. The
// dismissal is per user and per card id (lib/dismissals); once closed the
// card never renders again for that user on this browser.
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useDismissal } from "../lib/dismissals";

export function Dismissible({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) {
  const { dismissed, dismiss } = useDismissal(id);
  if (dismissed) return null;
  return (
    <div className="dismissible">
      <button
        type="button"
        className="dismiss-x"
        aria-label="Don't show this again"
        title="Don't show this again"
        onClick={dismiss}
      >
        <X size={14} strokeWidth={2} />
      </button>
      {children}
    </div>
  );
}
