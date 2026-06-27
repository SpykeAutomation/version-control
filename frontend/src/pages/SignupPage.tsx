import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Check } from "lucide-react";
import { AuthHeader } from "../components/AuthHeader";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

interface Requirement {
  label: string;
  ok: boolean;
}

function requirements(pw: string): Requirement[] {
  return [
    { label: "At least 8 characters", ok: pw.length >= 8 },
    { label: "One uppercase letter", ok: /[A-Z]/.test(pw) },
    { label: "One number", ok: /[0-9]/.test(pw) },
    { label: "One symbol", ok: /[^A-Za-z0-9]/.test(pw) },
  ];
}

export function SignupPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const reqs = useMemo(() => requirements(password), [password]);
  const passwordValid = reqs.every((r) => r.ok);
  const canSubmit = firstName && lastName && username && email && passwordValid;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    try {
      await register({
        email,
        name: `${firstName.trim()} ${lastName.trim()}`.trim(),
        username,
        password,
      });
      navigate("/onboarding", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="center-pane">
      <form className="auth-card" onSubmit={onSubmit}>
        <AuthHeader title="Create your account" />

        {error && <div className="form-error">{error}</div>}

        <div className="grid-2" style={{ marginBottom: 16 }}>
          <div>
            <label className="label" htmlFor="first">
              First name
            </label>
            <input
              id="first"
              className="input"
              autoComplete="given-name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="last">
              Last name
            </label>
            <input
              id="last"
              className="input"
              autoComplete="family-name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              required
            />
          </div>
        </div>

        <div className="field">
          <label className="label" htmlFor="username">
            Username
          </label>
          <input
            id="username"
            className="input"
            autoComplete="username"
            placeholder="jdoe"
            value={username}
            onChange={(e) =>
              setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))
            }
            required
          />
        </div>

        <div className="field">
          <label className="label" htmlFor="work-email">
            Work email
          </label>
          <input
            id="work-email"
            className="input"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <label className="label" htmlFor="new-password">
          Password
        </label>
        <input
          id="new-password"
          className="input"
          type="password"
          autoComplete="new-password"
          placeholder="Create a password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <div className="pw-reqs">
          {reqs.map((r) => (
            <div className="pw-req" key={r.label}>
              <span className={`pw-req-dot${r.ok ? " ok" : ""}`}>
                {r.ok && <Check size={11} color="#fff" strokeWidth={3} />}
              </span>
              <span className={r.ok ? "ok" : ""}>{r.label}</span>
            </div>
          ))}
        </div>

        <button
          className="btn btn-primary btn-block"
          type="submit"
          disabled={!canSubmit || submitting}
        >
          {submitting ? "Creating account…" : "Create account"}
        </button>

        <p className="fineprint">
          By continuing you agree to Spyke's <u>Terms</u> and <u>Privacy Policy</u>.
        </p>
        <p className="helper" style={{ marginTop: 20 }}>
          Already have an account?{" "}
          <Link to="/login" className="accent-link">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
