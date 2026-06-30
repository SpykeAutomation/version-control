import { Logo } from "./Logo";

export function BrandPanel() {
  return (
    <div className="brand">
      <div className="brand-logo">
        <Logo size={40} color="#fff" />
        <span className="brand-wordmark">spyke</span>
      </div>

      <div className="brand-body">
        <h1>Built for Automation Engineers.</h1>
      </div>

      <div className="brand-footer">© 2026 Spyke Automation</div>

      <div className="brand-chevrons" aria-hidden="true" />
    </div>
  );
}
