import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  delta?: string;
}

export function StatCard({ icon: Icon, label, value, delta }: StatCardProps) {
  return (
    <div className="stat-card">
      <span className="stat-icon">
        <Icon size={30} strokeWidth={2.2} />
      </span>
      <div className="stat-body">
        <span className="stat-label">{label}</span>
        <span className="stat-value">
          {value}
          {delta && <span className="stat-delta">{delta}</span>}
        </span>
      </div>
    </div>
  );
}
