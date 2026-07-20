// The two-letter monogram shown in avatar circles ("Jatin Hooda" → "JH").
export function initials(name: string | undefined): string {
  const p = (name ?? "").trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}
