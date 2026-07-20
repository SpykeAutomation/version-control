import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Book,
  ChevronsLeft,
  CirclePlay,
  GitBranch,
  Home,
  Layers,
  LogOut,
  Settings,
  Tag,
} from "lucide-react";
import { Logo } from "../components/Logo";
import { useAuth } from "../auth/AuthContext";
import { initials } from "../lib/initials";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/organization", label: "Organization", icon: Layers },
  { to: "/changes", label: "Changes", icon: GitBranch },
  { to: "/releases", label: "Releases", icon: Tag },
  { to: "/commissioning", label: "Commissioning", icon: CirclePlay },
  { to: "/documentation", label: "Documentation", icon: Book },
  { to: "/settings", label: "Settings", icon: Settings },
];

const COLLAPSE_KEY = "spyke_sidebar_collapsed";

export function Sidebar() {
  const { user, logout } = useAuth();
  const qc = useQueryClient();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === "1",
  );
  // The account menu anchored to the user block. Fixed-positioned (the rail
  // clips overflow), closed by the backdrop, Escape, or choosing an item.
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  // Logout is client-side: the backend has no web-session revocation, so
  // dropping the token ends the session. Clear the query cache too, so a
  // different account logging in never sees this one's cached data;
  // RequireAuth then redirects to /login on its own.
  const doLogout = () => {
    setMenuOpen(false);
    qc.clear();
    logout();
  };

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
          <button
            type="button"
            className="user-block user-block-btn"
            title={collapsed ? user.name : undefined}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            <span className="avatar">{initials(user.name)}</span>
            <div className="user-meta">
              <div className="user-name">{user.name}</div>
              <div className="user-sub">@{user.username ?? "user"}</div>
            </div>
          </button>

          {menuOpen && (
            <>
              <div
                className="account-backdrop"
                onClick={() => setMenuOpen(false)}
              />
              <div className="account-pop" role="menu" aria-label="Account">
                <div className="ap-head">
                  <span className="author-av">{initials(user.name)}</span>
                  <div className="ap-id">
                    <div className="ap-name">{user.name}</div>
                    <div className="ap-email" title={user.email}>
                      {user.email}
                    </div>
                  </div>
                </div>
                <Link
                  to="/settings"
                  className="ap-item"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                >
                  <Settings size={15} strokeWidth={1.8} />
                  Settings
                </Link>
                <Link
                  to="/documentation"
                  className="ap-item"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                >
                  <Book size={15} strokeWidth={1.8} />
                  Documentation
                </Link>
                <div className="ap-sep" />
                <button
                  type="button"
                  className="ap-item ap-logout"
                  role="menuitem"
                  onClick={doLogout}
                >
                  <LogOut size={15} strokeWidth={1.8} />
                  Log out
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </aside>
  );
}
