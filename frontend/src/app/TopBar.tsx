import { Search } from "lucide-react";
import type { ReactNode } from "react";

// Global top bar: search centered, page-provided actions on the right.
export function TopBar({ actions }: { actions?: ReactNode }) {
  return (
    <header className="topbar">
      <div className="topbar-col" />
      <div className="topbar-search">
        <Search size={16} strokeWidth={1.8} />
        <input
          placeholder="Search projects, controllers, tags…"
          aria-label="Search"
          disabled
          title="Search is coming soon"
        />
        <kbd>⌘K</kbd>
      </div>
      <div className="topbar-col topbar-actions">{actions}</div>
    </header>
  );
}
