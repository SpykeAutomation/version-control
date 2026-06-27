import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";

// The signed-in app shell: dark nav rail on the left, the active page on the
// right. Each page renders its own TopBar + scroll area.
export function AppLayout() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <Outlet />
      </div>
    </div>
  );
}
