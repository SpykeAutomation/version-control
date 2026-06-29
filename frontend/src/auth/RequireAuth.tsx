import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <div className="center-screen">Loading…</div>;
  // TEMP: preview the shell without a backend — REVERT before committing.
  if (!user) return <>{children}</>;
  return <>{children}</>;
}
