import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthLayout } from "./layouts/AuthLayout";
import { AppLayout } from "./app/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { SignupPage } from "./pages/SignupPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { DonePage } from "./pages/DonePage";
import { CliAuthPage } from "./pages/CliAuthPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RepositoryPage } from "./pages/RepositoryPage";
import { BranchesPage } from "./pages/BranchesPage";
import { CommitsPage } from "./pages/CommitsPage";
import { CommitPage } from "./pages/CommitPage";
import { CommitReviewPage } from "./pages/CommitReviewPage";
import { RevertPage } from "./pages/RevertPage";
import { FileViewPage } from "./pages/FileViewPage";
import { ComparePage } from "./pages/ComparePage";
import { MergeRequestPage } from "./pages/MergeRequestPage";
import { CreateMergeRequestPage } from "./pages/CreateMergeRequestPage";
import { ComingSoon } from "./pages/ComingSoon";
import { RequireAuth } from "./auth/RequireAuth";

export function App() {
  return (
    <Routes>
      {/* Auth + onboarding: split brand-panel layout */}
      <Route element={<AuthLayout />}>
        <Route index element={<Navigate to="/login" replace />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="signup" element={<SignupPage />} />
        <Route
          path="onboarding"
          element={
            <RequireAuth>
              <OnboardingPage />
            </RequireAuth>
          }
        />
        <Route
          path="done"
          element={
            <RequireAuth>
              <DonePage />
            </RequireAuth>
          }
        />
        <Route
          path="cli-auth"
          element={
            <RequireAuth>
              <CliAuthPage />
            </RequireAuth>
          }
        />
      </Route>

      {/* Signed-in app: three-zone shell */}
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="dashboard" element={<ComingSoon title="Dashboard" />} />
        <Route path="organization" element={<ProjectsPage />} />
        <Route path="organization/:slug" element={<RepositoryPage />} />
        <Route path="organization/:slug/branches" element={<BranchesPage />} />
        <Route path="organization/:slug/commits" element={<CommitsPage />} />
        <Route path="organization/:slug/commit" element={<CommitPage />} />
        <Route path="organization/:slug/commit/:sha" element={<CommitReviewPage />} />
        <Route path="organization/:slug/revert" element={<RevertPage />} />
        <Route path="organization/:slug/files/:fileName" element={<FileViewPage />} />
        <Route
          path="organization/:slug/merge-requests/new"
          element={<CreateMergeRequestPage />}
        />
        <Route path="organization/:slug/merge/:mrId" element={<MergeRequestPage />} />
        {/* Old bookmarks and shared links: /projects/* moved to /organization/*. */}
        <Route path="projects/*" element={<LegacyProjectsRedirect />} />
        <Route path="projects" element={<LegacyProjectsRedirect />} />
        <Route path="changes" element={<ComingSoon title="Changes" />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="releases" element={<ComingSoon title="Releases" />} />
        <Route path="commissioning" element={<ComingSoon title="Commissioning" />} />
        <Route path="documentation" element={<ComingSoon title="Documentation" />} />
        <Route path="settings" element={<ComingSoon title="Settings" />} />
      </Route>

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

// Rewrites a legacy /projects/... URL onto /organization/..., keeping the
// rest of the path, the query string and the hash intact.
function LegacyProjectsRedirect() {
  const { pathname, search, hash } = useLocation();
  const to = pathname.replace(/^\/projects/, "/organization") + search + hash;
  return <Navigate to={to} replace />;
}
