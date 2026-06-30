import { useState, type ReactNode } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { TopBarActionsProvider } from "./TopBarActions";

// The signed-in app shell: dark nav rail on the left, the shared top bar, then
// the active page. The top bar lives here (not per page) so every page gets the
// same header; pages add their own buttons via useTopBarActions.
export function AppLayout() {
  const [actions, setActions] = useState<ReactNode>(null);
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <TopBar actions={actions} />
        <TopBarActionsProvider value={setActions}>
          <Outlet />
        </TopBarActionsProvider>
      </div>
    </div>
  );
}
