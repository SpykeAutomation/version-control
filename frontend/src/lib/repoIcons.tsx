// The eight repository icons: PLC-flavoured glyphs, each with a fixed colour
// tone so a repository reads identically everywhere it appears (table rows,
// page headers, pickers). A repo without a stored icon (backend field pending
// deploy, or legacy rows) falls back to a stable slug-hash pick — no repo is
// ever iconless, and existing repos keep the icon they've always shown.
import type { ReactNode } from "react";

// The backend stores the icon as an INTEGER 1..30 (0 and >30 are rejected).
// The code->look mapping is defined here and only here: ten glyphs x three
// colour tones, code = 1 + glyphIndex * 3 + toneIndex. Glyph order:
// 0 controller, 1 ladder, 2 motion, 3 conveyor, 4 robot-arm, 5 sensor,
// 6 power, 7 network, 8 gauge, 9 valve. Tone order: 0 blue, 1 green, 2 amber.
export interface RepoGlyphDef {
  label: string;
  glyph: (size: number) => ReactNode;
}

export const REPO_TONES = ["blue", "green", "amber"] as const;

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

export const REPO_GLYPHS: RepoGlyphDef[] = [
  {
    label: "Controller",
    glyph: (s) => (
      <Svg size={s}>
        <rect x="7" y="6" width="10" height="12" rx="1.5" />
        <path d="M4.5 9.5H7M4.5 12H7M4.5 14.5H7M17 9.5h2.5M17 12h2.5M17 14.5h2.5" />
      </Svg>
    ),
  },
  {
    label: "Ladder logic",
    glyph: (s) => (
      <Svg size={s}>
        <path d="M6 4v16M18 4v16" />
        <path d="M6 9h12" />
        <path d="M6 15h4.5M13.5 15h4.5M10.5 13v4M13.5 13v4" />
      </Svg>
    ),
  },
  {
    label: "Motion",
    glyph: (s) => (
      <Svg size={s}>
        <circle cx="12" cy="13" r="6.5" />
        <circle cx="12" cy="13" r="1.6" fill="currentColor" stroke="none" />
        <path d="M12 3.5v3" />
      </Svg>
    ),
  },
  {
    label: "Conveyor",
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
    label: "Robot arm",
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
    label: "Sensor",
    glyph: (s) => (
      <Svg size={s}>
        <circle cx="8" cy="12" r="1.7" fill="currentColor" stroke="none" />
        <path d="M11.5 8.5a5 5 0 0 1 0 7" />
        <path d="M14.5 5.5a9.5 9.5 0 0 1 0 13" />
      </Svg>
    ),
  },
  {
    label: "Power",
    glyph: (s) => (
      <Svg size={s}>
        <rect x="6.5" y="4" width="11" height="16" rx="2" />
        <path d="M13.5 7.5l-2.8 4.9h3.2l-2.7 4.4" />
      </Svg>
    ),
  },
  {
    label: "Network",
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
  {
    label: "Gauge",
    glyph: (s) => (
      <Svg size={s}>
        <circle cx="12" cy="13" r="7" />
        <path d="M12 13l3.4-3.9" />
        <circle cx="12" cy="13" r="1.4" fill="currentColor" stroke="none" />
        <path d="M6.8 9.5l-1.2-.8M17.2 9.5l1.2-.8" />
      </Svg>
    ),
  },
  {
    label: "Valve",
    glyph: (s) => (
      <Svg size={s}>
        <path d="M5 9.5l7 3.5-7 3.5zM19 9.5l-7 3.5 7 3.5z" />
        <path d="M12 13V7.5" />
        <path d="M9 7.5h6" />
      </Svg>
    ),
  },
];

export const ICON_CODE_MAX = REPO_GLYPHS.length * REPO_TONES.length; // 30

export function encodeRepoIcon(glyphIndex: number, toneIndex: number): number {
  return 1 + glyphIndex * REPO_TONES.length + toneIndex;
}

export function decodeRepoIcon(
  code: number | null | undefined,
): { glyphIndex: number; toneIndex: number } | null {
  if (
    typeof code !== "number" ||
    !Number.isInteger(code) ||
    code < 1 ||
    code > ICON_CODE_MAX
  ) {
    return null;
  }
  const n = code - 1;
  return {
    glyphIndex: Math.floor(n / REPO_TONES.length),
    toneIndex: n % REPO_TONES.length,
  };
}

// The stored code when valid, else a stable slug-hash fallback (legacy rows
// and the window before the backend carries the field).
export function resolveRepoIcon(
  icon: number | null | undefined,
  slug: string,
): { code: number; label: string; tone: string; glyph: (s: number) => ReactNode } {
  let decoded = decodeRepoIcon(icon);
  let code = icon as number;
  if (!decoded) {
    let h = 0;
    for (let i = 0; i < slug.length; i += 1)
      h = (h * 31 + slug.charCodeAt(i)) >>> 0;
    code = (h % ICON_CODE_MAX) + 1;
    decoded = decodeRepoIcon(code)!;
  }
  const g = REPO_GLYPHS[decoded.glyphIndex];
  return {
    code,
    label: g.label,
    tone: REPO_TONES[decoded.toneIndex],
    glyph: g.glyph,
  };
}

export function randomRepoIconId(): number {
  return 1 + Math.floor(Math.random() * ICON_CODE_MAX);
}

export function RepoIcon({
  icon,
  slug,
  size,
  className,
}: {
  icon?: number | null;
  slug: string;
  size: number;
  className: string;
}) {
  const def = resolveRepoIcon(icon, slug);
  return <span className={`${className} tone-${def.tone}`}>{def.glyph(size)}</span>;
}
