import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle2, ShieldAlert } from "lucide-react";
import logoUrl from "../assets/logo.png";
import { useAuth } from "../auth/AuthContext";
import { approveDevice } from "../api/auth";
import { ApiError } from "../api/client";

// Normalize a user code for display and submission: drop all whitespace
// (including a stray space pasted mid-code) and uppercase it. The CLI prints
// codes like "WDJB-MJHT".
function normalize(raw: string): string {
  return raw.replace(/\s+/g, "").toUpperCase();
}

// True when we're rendered inside an iframe. Approving signs a CLI into the
// user's account, so a framed render is almost certainly a clickjacking attempt
// — we refuse to show the approval UI. A cross-origin frame throws on access,
// which we also treat as framed.
function isFramed(): boolean {
  try {
    return window.top !== window.self;
  } catch {
    return true;
  }
}

type Status = "idle" | "submitting" | "approved";

export function CliAuthPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  // Capture the URL code once, then scrub it from the address bar so the code
  // doesn't linger in browser history or leak via the Referer header. We keep
  // working from the captured value, not the live query string.
  const [urlCode] = useState(() => params.get("code"));
  const fromUrl = urlCode != null && normalize(urlCode) !== "";
  const [originalHref] = useState(() => window.location.href);

  const [typedCode, setTypedCode] = useState("");
  const code = fromUrl ? normalize(urlCode as string) : normalize(typedCode);

  const [confirmed, setConfirmed] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (urlCode != null) navigate("/cli-auth", { replace: true });
    // Run once on mount; navigate/urlCode are stable for this purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const who = user?.name || user?.email || "your account";

  async function onApprove(e: FormEvent) {
    e.preventDefault();
    if (!code) {
      setError("Enter the code shown in your terminal.");
      return;
    }
    setError(null);
    setStatus("submitting");
    try {
      await approveDevice(code);
      setStatus("approved");
    } catch (err) {
      setStatus("idle");
      if (err instanceof ApiError && err.status === 400) {
        setError("This code is invalid or expired. Run spyke login again.");
      } else if (err instanceof ApiError && err.status === 409) {
        setError("This request was already approved.");
      } else {
        setError(
          err instanceof ApiError ? err.message : "Something went wrong.",
        );
      }
    }
  }

  // Refuse to run inside a frame — defeats clickjacking the one-click Approve.
  if (isFramed()) {
    return (
      <div className="center-pane">
        <div className="auth-card cli-card">
          <div className="cli-badge cli-badge-warn">
            <ShieldAlert size={20} strokeWidth={1.8} />
          </div>
          <h2 className="auth-title">Open Spyke directly</h2>
          <p className="cli-lead" style={{ textAlign: "center" }}>
            This sign-in approval can't be completed inside another site. Open
            the link directly in your browser to continue.
          </p>
          <a className="btn btn-primary btn-block" href={originalHref} target="_top">
            Open the approval page
          </a>
        </div>
      </div>
    );
  }

  if (status === "approved") {
    return (
      <div className="center-pane">
        <div className="auth-card cli-card">
          <div className="cli-done-icon">
            <CheckCircle2 size={52} color="var(--add)" strokeWidth={1.7} />
          </div>
          <h2 className="auth-title" style={{ marginBottom: 12 }}>
            You're all set
          </h2>
          <p className="cli-lead" style={{ textAlign: "center" }}>
            Return to your terminal — the CLI will pick up your sign-in
            automatically. You can close this tab.
          </p>
        </div>
      </div>
    );
  }

  const submitting = status === "submitting";

  return (
    <div className="center-pane">
      <form className="auth-card cli-card" onSubmit={onApprove}>
        <div className="cli-marks">
          <img className="cli-logo" src={logoUrl} alt="Spyke" />
        </div>
        <h2 className="auth-title">Approve CLI sign-in</h2>

        {error && <div className="form-error">{error}</div>}

        <p className="cli-lead">
          A command-line device wants to sign in to Spyke as{" "}
          <strong>{who}</strong>. Approving gives that terminal full access to
          your account. Only approve if you just ran{" "}
          <code className="cli-cmd">spyke login</code> yourself on this computer
          and the code below matches your terminal — never a code someone sent
          you in a link or message.
        </p>

        {fromUrl ? (
          <div className="cli-code" aria-label="Device code">
            {code}
          </div>
        ) : (
          <div className="field">
            <label className="label" htmlFor="cli-code">
              Code from your terminal
            </label>
            <input
              id="cli-code"
              className="input mono"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={24}
              placeholder="WDJB-MJHT"
              value={typedCode}
              onChange={(e) => setTypedCode(e.target.value)}
            />
          </div>
        )}

        <label className="cli-confirm">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          <span>I started this sign-in on this computer just now.</span>
        </label>

        <div className="cli-actions">
          <button
            className="btn btn-primary btn-block"
            type="submit"
            disabled={submitting || !code || !confirmed}
          >
            {submitting ? "Approving…" : "Approve"}
          </button>
          <button
            className="btn btn-ghost btn-block"
            type="button"
            onClick={() => navigate("/organization")}
            disabled={submitting}
          >
            Cancel
          </button>
        </div>

        <p className="helper">
          Didn't start this? You can safely close this tab — nothing is signed
          in until you approve.
        </p>
      </form>
    </div>
  );
}
