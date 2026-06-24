import { Outlet } from "react-router-dom";
import { BrandPanel } from "../components/BrandPanel";

// Split-screen shell: dark brand panel on the left, the active flow on the right.
export function AuthLayout() {
  return (
    <div className="split">
      <BrandPanel />
      <div className="flow">
        <Outlet />
      </div>
    </div>
  );
}
