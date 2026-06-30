import { Logo } from "./Logo";

// The centered logo mark + title used at the top of the sign-in / sign-up cards.
export function AuthHeader({ title }: { title: string }) {
  return (
    <>
      <div className="auth-logo">
        <div className="auth-mark">
          <Logo size={22} color="#fff" />
        </div>
      </div>
      <h2 className="auth-title">{title}</h2>
    </>
  );
}
