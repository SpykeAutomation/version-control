// Small display formatters shared across pages, so the same value never
// renders two different ways depending on where it appears.

// Human-readable byte size for size columns and upload rows.
export function formatBytes(n: number): string {
  if (n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  const v = n / 1024 ** i;
  return `${i === 0 ? v : v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}

// The 7-character short form of a commit sha.
export function shortSha(sha: string): string {
  return sha.slice(0, 7);
}
