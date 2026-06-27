import type { ReactNode } from "react";

interface RailSectionProps {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}

// A stacked section in the right rail: a titled card with a list body.
export function RailSection({ title, action, children }: RailSectionProps) {
  return (
    <section className="rail-section">
      <div className="rail-head">
        <span className="rail-title">{title}</span>
        {action}
      </div>
      <div className="rail-body">{children}</div>
    </section>
  );
}
