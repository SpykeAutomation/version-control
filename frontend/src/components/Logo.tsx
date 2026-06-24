interface LogoProps {
  size?: number;
  color?: string;
  strokeWidth?: number;
}

// The Spyke mark: two stacked upward chevrons. Geometry matches the chevron
// used on spykeautomation.com (same path + stroke proportions).
export function Logo({ size = 24, color = "currentColor", strokeWidth = 13 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 -2 100 100" fill="none" aria-hidden="true">
      <g
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M22 46 50 22 78 46" />
        <path d="M22 74 50 50 78 74" />
      </g>
    </svg>
  );
}
