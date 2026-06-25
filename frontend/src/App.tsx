import { Navigate, Route, Routes } from "react-router-dom";
import { AuthLayout } from "./layouts/AuthLayout";
import { AppLayout } from "./app/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { SignupPage } from "./pages/SignupPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { DonePage } from "./pages/DonePage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RepositoryPage } from "./pages/RepositoryPage";
import { CommitPage } from "./pages/CommitPage";
import { FileViewPage } from "./pages/FileViewPage";
import { BranchViewPage } from "./pages/BranchViewPage";
import { ComparePage } from "./pages/ComparePage";
import { MergeRequestPage } from "./pages/MergeRequestPage";
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
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:slug" element={<RepositoryPage />} />
        <Route path="projects/:slug/commit" element={<CommitPage />} />
        <Route path="projects/:slug/files/:fileName" element={<FileViewPage />} />
        <Route path="projects/:slug/tree/:branch" element={<BranchViewPage />} />
        <Route path="projects/:slug/merge/:mrId" element={<MergeRequestPage />} />
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
