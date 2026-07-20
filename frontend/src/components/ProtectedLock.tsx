// The marker shown next to a protected branch: a lock icon whose hover
// tooltip reads "Protected branch", instead of a "protected" text badge, so
// branch rows stay compact and the state reads at a glance.
import { Lock } from "lucide-react";
import type { CSSProperties } from "react";

export function ProtectedLock({
  size = 13,
  style,
}: {
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <span
      className="branch-lock"
      title="Protected branch"
      aria-label="Protected branch"
      style={style}
    >
      <Lock size={size} strokeWidth={2} />
    </span>
  );
}
