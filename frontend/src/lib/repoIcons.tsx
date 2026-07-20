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
// 6 power, 7 network, 8 gauge, 9 valve. Tone order: 0 blue, 1 green, 2 red.
export interface RepoGlyphDef {
  label: string;
  glyph: (size: number) => ReactNode;
}

export const REPO_TONES = ["blue", "green", "red"] as const;

function Svg({ size, children }: { size: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

// Chunky flat style: solid fills (holes cut with evenodd so the tile shows
// through) plus fat round strokes where a line reads better than a shape.
// Solid shapes antialias cleanly at any render size — unlike the earlier
// thin-stroke set, no blessed-size rule is needed.
const F = "currentColor";
const line = { stroke: "currentColor", strokeWidth: 2.4, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export const REPO_GLYPHS: RepoGlyphDef[] = [
  {
    label: "Controller",
    glyph: (s) => (
      <Svg size={s}>
        <path
          fill={F}
          fillRule="evenodd"
          d="M9 5h6a2.2 2.2 0 0 1 2.2 2.2v9.6A2.2 2.2 0 0 1 15 19H9a2.2 2.2 0 0 1-2.2-2.2V7.2A2.2 2.2 0 0 1 9 5zm1.6 4.6v4.8h2.8V9.6z"
        />
        <path {...line} strokeWidth={2} d="M4.3 8.5h1.6M4.3 12h1.6M4.3 15.5h1.6M18.1 8.5h1.6M18.1 12h1.6M18.1 15.5h1.6" />
      </Svg>
    ),
  },
  {
    label: "Ladder logic",
    glyph: (s) => (
      <Svg size={s}>
        <path {...line} strokeWidth={2.6} d="M7 4v16M17 4v16" />
        <path {...line} strokeWidth={2.4} d="M7 9h10M7 15h10" />
      </Svg>
    ),
  },
  {
    label: "Motion",
    glyph: (s) => (
      <Svg size={s}>
        <path
          fill={F}
          fillRule="evenodd"
          d="M12 6a7 7 0 1 1 0 14 7 7 0 0 1 0-14zm0 4.8a2.2 2.2 0 1 0 0 4.4 2.2 2.2 0 0 0 0-4.4z"
        />
        <path {...line} d="M12 3.2v2" />
      </Svg>
    ),
  },
  {
    label: "Conveyor",
    glyph: (s) => (
      <Svg size={s}>
        <rect x="8.75" y="4.6" width="6.5" height="5.2" rx="1.2" fill={F} />
        <path
          fill={F}
          fillRule="evenodd"
          d="M6.75 12h10.5a2.75 2.75 0 1 1 0 5.5H6.75a2.75 2.75 0 1 1 0-5.5zm1.75 1.45a1.3 1.3 0 1 0 0 2.6 1.3 1.3 0 0 0 0-2.6zm7 0a1.3 1.3 0 1 0 0 2.6 1.3 1.3 0 0 0 0-2.6z"
        />
      </Svg>
    ),
  },
  {
    label: "Robot arm",
    glyph: (s) => (
      <Svg size={s}>
        <path {...line} strokeWidth={2.6} d="M6.5 20h8" />
        <path {...line} strokeWidth={2.6} d="M9.5 19.5V13l6-4" />
        <circle cx="9.5" cy="13" r="2" fill={F} />
        <circle cx="15.5" cy="9" r="1.8" fill={F} />
        <path {...line} strokeWidth={2} d="M17 8l2.2-1.6M17.2 9.6l2.6.7" />
      </Svg>
    ),
  },
  {
    label: "Sensor",
    glyph: (s) => (
      <Svg size={s}>
        <circle cx="7.5" cy="12" r="2.3" fill={F} />
        <path {...line} d="M11.5 8.4a5.1 5.1 0 0 1 0 7.2" />
        <path {...line} d="M14.7 5.4a9.6 9.6 0 0 1 0 13.2" />
      </Svg>
    ),
  },
  {
    label: "Power",
    glyph: (s) => (
      <Svg size={s}>
        <path
          fill={F}
          fillRule="evenodd"
          d="M9 4h6a2.4 2.4 0 0 1 2.4 2.4v11.2A2.4 2.4 0 0 1 15 20H9a2.4 2.4 0 0 1-2.4-2.4V6.4A2.4 2.4 0 0 1 9 4zm4.5 3-3.7 5.7h2.6l-1.2 4.3 3.9-5.9h-2.6z"
        />
      </Svg>
    ),
  },
  {
    label: "Network",
    glyph: (s) => (
      <Svg size={s}>
        <path {...line} d="M4 17.5h16" />
        <path {...line} strokeWidth={2} d="M7 17.5v-6M12 17.5V9M17 17.5v-6" />
        <circle cx="7" cy="9.2" r="2.2" fill={F} />
        <circle cx="12" cy="6.7" r="2.2" fill={F} />
        <circle cx="17" cy="9.2" r="2.2" fill={F} />
      </Svg>
    ),
  },
  {
    label: "Gauge",
    glyph: (s) => (
      <Svg size={s}>
        <path
          fill={F}
          fillRule="evenodd"
          d="M12 6a7 7 0 1 1 0 14 7 7 0 0 1 0-14zm0 2.6a4.4 4.4 0 1 0 0 8.8 4.4 4.4 0 0 0 0-8.8z"
        />
        <circle cx="12" cy="13" r="1.7" fill={F} />
        <path {...line} d="M12 13l3.2-3.7" />
      </Svg>
    ),
  },
  {
    label: "Valve",
    glyph: (s) => (
      <Svg size={s}>
        <path fill={F} d="M4.5 9.5v7a.9.9 0 0 0 1.3.8l6.2-3.3 6.2 3.3a.9.9 0 0 0 1.3-.8v-7a.9.9 0 0 0-1.3-.8L12 12 5.8 8.7a.9.9 0 0 0-1.3.8z" />
        <path {...line} d="M12 12.5V7.8" />
        <path {...line} d="M9.2 7.8h5.6" />
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
