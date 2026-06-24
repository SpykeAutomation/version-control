import { Search } from "lucide-react";
import type { ReactNode } from "react";

// Global top bar: search on the left, page-provided actions on the right.
export function TopBar({ actions }: { actions?: ReactNode }) {
  return (
    <header className="topbar">
      <div className="topbar-search">
        <Search size={16} strokeWidth={1.8} />
        <input placeholder="Search projects, controllers, tags…" aria-label="Search" />
        <kbd>⌘K</kbd>
      </div>
      {actions && <div className="topbar-actions">{actions}</div>}
    </header>
  );
}
