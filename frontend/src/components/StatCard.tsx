import type { LucideIcon } from "lucide-react";
import { ArrowDown, ArrowUp } from "lucide-react";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  delta?: string;
  sub?: string;
  trend?: { value: string; dir: "up" | "down" };
}

export function StatCard({ icon: Icon, label, value, delta, sub, trend }: StatCardProps) {
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
        {trend ? (
          <span className={`stat-trend ${trend.dir}`}>
            {trend.dir === "up" ? (
              <ArrowUp size={13} strokeWidth={2.2} />
            ) : (
              <ArrowDown size={13} strokeWidth={2.2} />
            )}
            {trend.value}
          </span>
        ) : sub ? (
          <span className="stat-sub">{sub}</span>
        ) : null}
      </div>
    </div>
  );
}
