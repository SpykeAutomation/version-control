import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AuthHeader } from "../components/AuthHeader";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: Location })?.from?.pathname ?? "/onboarding";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="center-pane">
      <form className="auth-card" onSubmit={onSubmit}>
        <AuthHeader title="Sign in to Spyke" />

        {error && <div className="form-error">{error}</div>}

        <div className="field">
          <label className="label" htmlFor="email">
            Email address
          </label>
          <input
            id="email"
            className="input"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="field">
          <div className="row-between">
            <label className="label" style={{ margin: 0 }} htmlFor="password">
              Password
            </label>
            <span className="link">Forgot password?</span>
          </div>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <button
          className="btn btn-primary btn-block"
          type="submit"
          disabled={submitting}
          style={{ marginTop: 4 }}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <p className="helper">
          Spyke is invite-only during early access.{" "}
          <a
            className="accent-link"
            href="https://www.spykeautomation.com/"
            target="_blank"
            rel="noreferrer"
          >
            Request access
          </a>
        </p>
      </form>
    </div>
  );
}
