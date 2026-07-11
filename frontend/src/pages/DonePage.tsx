import { Link, useLocation } from "react-router-dom";
import {
  ArrowRight,
  BadgeCheck,
  Code2,
  Cpu,
  GitBranch,
  GitCompare,
  Rocket,
  UploadCloud,
  type LucideIcon,
} from "lucide-react";

interface DoneState {
  projectId?: number;
  projectName?: string;
}

interface Doc {
  title: string;
  sub: string;
  icon: LucideIcon;
}

const DOCS: Doc[] = [
  {
    title: "Quickstart",
    sub: "Set up your first repo in 5 minutes",
    icon: Rocket,
  },
  {
    title: "Connect controllers",
    sub: "Link Siemens, CODESYS, Rockwell & more",
    icon: Cpu,
  },
  {
    title: "Branching & PRs",
    sub: "Review and merge PLC code safely",
    icon: GitBranch,
  },
  {
    title: "Visual diffs",
    sub: "Read ladder & structured-text changes",
    icon: GitCompare,
  },
  {
    title: "Deploy & rollback",
    sub: "Push to a controller, revert in one click",
    icon: UploadCloud,
  },
  {
    title: "API reference",
    sub: "Automate with the Spyke REST API",
    icon: Code2,
  },
];

export function DonePage() {
  const { state } = useLocation();
  const { projectName } = (state as DoneState | null) ?? {};
  const repoHref = "/organization";

  return (
    <div className="done">
      <div className="done-card">
        <div className="done-icon">
          <BadgeCheck size={58} color="var(--add)" strokeWidth={1.6} />
        </div>
        <h2>You're all set</h2>
        <p>
          {projectName ? (
            <>
              <strong>{projectName}</strong> is ready. Upload your first L5X export to
              create the initial commit on the main branch.
            </>
          ) : (
            <>
              Your project is ready. Upload your first L5X export to create the initial
              commit on the main branch.
            </>
          )}
        </p>
        <Link to={repoHref} className="btn btn-primary" style={{ height: 44 }}>
          Go to project →
        </Link>
      </div>

      <div className="docs">
        <div className="docs-head">
          <span>Explore the docs</span>
          <div className="rule" />
        </div>
        <div className="docs-grid">
          {DOCS.map((d) => {
            const Icon = d.icon;
            return (
              <a className="doc-card" href="#" key={d.title}>
                <div className="doc-icon">
                  <Icon size={16} strokeWidth={1.8} />
                </div>
                <div className="doc-title">
                  {d.title}
                  <ArrowRight size={13} color="var(--ink3)" />
                </div>
                <div className="doc-sub">{d.sub}</div>
              </a>
            );
          })}
        </div>
      </div>
    </div>
  );
}
