import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

// Landing spot after onboarding. The repository view itself is a separate
// feature; this keeps "Go to repository" from being a dead link.
export function RepositoryPlaceholder() {
  const { logout } = useAuth();
  return (
    <div className="center-screen" style={{ flexDirection: "column", gap: 14 }}>
      <div>Repository view coming soon.</div>
      <Link to="/login" className="link" onClick={() => logout()}>
        Sign out
      </Link>
    </div>
  );
}
