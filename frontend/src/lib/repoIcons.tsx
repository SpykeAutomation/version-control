// The eight repository icons: PLC-flavoured glyphs, each with a fixed colour
// tone so a repository reads identically everywhere it appears (table rows,
// page headers, pickers). A repo without a stored icon (backend field pending
// deploy, or legacy rows) falls back to a stable slug-hash pick — no repo is
// ever iconless, and existing repos keep the icon they've always shown.
import type { ReactNode } from "react";

export interface RepoIconDef {
  id: string;
  label: string;
  tone: string;
  glyph: (size: number) => ReactNode;
}

function Svg({ size, children }: { size: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const REPO_ICONS: RepoIconDef[] = [
  {
    id: "controller",
    label: "Controller",
    tone: "blue",
    glyph: (s) => (
      <Svg size={s}>
        <rect x="7" y="6" width="10" height="12" rx="1.5" />
        <path d="M4.5 9.5H7M4.5 12H7M4.5 14.5H7M17 9.5h2.5M17 12h2.5M17 14.5h2.5" />
      </Svg>
    ),
  },
  {
    id: "ladder",
    label: "Ladder logic",
    tone: "green",
    glyph: (s) => (
      <Svg size={s}>
        <path d="M6 4v16M18 4v16" />
        <path d="M6 9h12" />
        <path d="M6 15h4.5M13.5 15h4.5M10.5 13v4M13.5 13v4" />
      </Svg>
    ),
  },
  {
    id: "motion",
    label: "Motion",
    tone: "violet",
    glyph: (s) => (
      <Svg size={s}>
        <circle cx="12" cy="13" r="6.5" />
        <circle cx="12" cy="13" r="1.6" fill="currentColor" stroke="none" />
        <path d="M12 3.5v3" />
      </Svg>
    ),
  },
  {
    id: "conveyor",
    label: "Conveyor",
    tone: "amber",
    glyph: (s) => (
      <Svg size={s}>
        <rect x="9" y="5" width="6" height="4.5" rx="1" />
        <rect x="4" y="12.5" width="16" height="5" rx="2.5" />
        <circle cx="8.5" cy="15" r="1.2" />
        <circle cx="15.5" cy="15" r="1.2" />
      </Svg>
    ),
  },
  {
    id: "robot-arm",
    label: "Robot arm",
    tone: "slate",
    glyph: (s) => (
      <Svg size={s}>
        <path d="M6.5 20h8" />
        <path d="M9.5 20v-5.5" />
        <circle cx="9.5" cy="13" r="1.5" />
        <path d="M10.8 12.1l4-3.1" />
        <circle cx="16" cy="8.2" r="1.4" />
        <path d="M17.3 7.5l2.2-1.7M17.4 8.8l2.7.8" />
      </Svg>
    ),
  },
  {
    id: "sensor",
    label: "Sensor",
    tone: "teal",
    glyph: (s) => (
      <Svg size={s}>
        <circle cx="8" cy="12" r="1.7" fill="currentColor" stroke="none" />
        <path d="M11.5 8.5a5 5 0 0 1 0 7" />
        <path d="M14.5 5.5a9.5 9.5 0 0 1 0 13" />
      </Svg>
    ),
  },
  {
    id: "power",
    label: "Power",
    tone: "orange",
    glyph: (s) => (
      <Svg size={s}>
        <rect x="6.5" y="4" width="11" height="16" rx="2" />
        <path d="M13.5 7.5l-2.8 4.9h3.2l-2.7 4.4" />
      </Svg>
    ),
  },
  {
    id: "network",
    label: "Network",
    tone: "indigo",
    glyph: (s) => (
      <Svg size={s}>
        <path d="M4 17.5h16" />
        <path d="M7 17.5V11M12 17.5V8.5M17 17.5V11" />
        <circle cx="7" cy="9.3" r="1.7" />
        <circle cx="12" cy="6.8" r="1.7" />
        <circle cx="17" cy="9.3" r="1.7" />
      </Svg>
    ),
  },
];

// The stored id when it's one of ours, else a stable slug-hash fallback.
export function resolveRepoIcon(
  icon: string | null | undefined,
  slug: string,
): RepoIconDef {
  const found = icon ? REPO_ICONS.find((i) => i.id === icon) : undefined;
  if (found) return found;
  let h = 0;
  for (let i = 0; i < slug.length; i += 1) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return REPO_ICONS[h % REPO_ICONS.length];
}

export function randomRepoIconId(): string {
  return REPO_ICONS[Math.floor(Math.random() * REPO_ICONS.length)].id;
}

export function RepoIcon({
  icon,
  slug,
  size,
  className,
}: {
  icon?: string | null;
  slug: string;
  size: number;
  className: string;
}) {
  const def = resolveRepoIcon(icon, slug);
  return <span className={`${className} tone-${def.tone}`}>{def.glyph(size)}</span>;
}
