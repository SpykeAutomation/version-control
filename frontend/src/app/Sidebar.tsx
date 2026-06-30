import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  Book,
  ChevronsLeft,
  CirclePlay,
  GitBranch,
  Home,
  Layers,
  Settings,
  Tag,
} from "lucide-react";
import { Logo } from "../components/Logo";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/projects", label: "Projects", icon: Layers },
  { to: "/changes", label: "Changes", icon: GitBranch },
  { to: "/releases", label: "Releases", icon: Tag },
  { to: "/commissioning", label: "Commissioning", icon: CirclePlay },
  { to: "/documentation", label: "Documentation", icon: Book },
  { to: "/settings", label: "Settings", icon: Settings },
];

const COLLAPSE_KEY = "spyke_sidebar_collapsed";

function initials(name: string | undefined): string {
  const parts = (name ?? "").trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function Sidebar() {
  const { user } = useAuth();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === "1",
  );

  function toggle() {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }

  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      <div className="sidebar-logo">
        {/* The brand mark toggles the rail (rotates to point right when
            collapsed); the chevron does the same and fades out when collapsed.
            Both stay mounted so the rail can animate width without the content
            popping in and out. */}
        <button
          className="sidebar-mark sidebar-mark-btn"
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <Logo size={26} color="#fff" />
        </button>
        <span className="sidebar-word">spyke</span>
        <button
          className="sidebar-collapse"
          onClick={toggle}
          aria-label="Collapse sidebar"
          tabIndex={collapsed ? -1 : 0}
        >
          <ChevronsLeft size={16} strokeWidth={2} />
        </button>
      </div>

      <nav className="sidebar-nav">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            <Icon size={18} strokeWidth={1.8} />
            <span className="nav-label">{label}</span>
          </NavLink>
        ))}
      </nav>

      {user && (
        <div className="sidebar-foot">
          <div className="user-block" title={collapsed ? user.name : undefined}>
            <span className="avatar">{initials(user.name)}</span>
            <div className="user-meta">
              <div className="user-name">{user.name}</div>
              <div className="user-sub">@{user.username ?? "user"}</div>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
