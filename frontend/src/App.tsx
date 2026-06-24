import { Navigate, Route, Routes } from "react-router-dom";
import { AuthLayout } from "./layouts/AuthLayout";
import { LoginPage } from "./pages/LoginPage";
import { SignupPage } from "./pages/SignupPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { DonePage } from "./pages/DonePage";
import { RepositoryPlaceholder } from "./pages/RepositoryPlaceholder";
import { RequireAuth } from "./auth/RequireAuth";

export function App() {
  return (
    <Routes>
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
      <Route
        path="projects/*"
        element={
          <RequireAuth>
            <RepositoryPlaceholder />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
