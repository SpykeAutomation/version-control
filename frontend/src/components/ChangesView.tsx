// Shared building blocks for the two review pages' change lists (the
// merge-request Changes tab and the commit Changes tab): a per-file section of
// routine diffs, the structured-text code diff, and the zoom control. Ladder
// rungs draw through LadderDiff; everything here is presentational.
import { FileCode2, Minus, Plus } from "lucide-react";
import { RoutineLadderDiffView } from "./LadderDiff";
import type { MRCodeDiff, PRFile, PRRoutineChange } from "../api/mergeRequest";

// One changed L5X file: a numbered header naming the file, then each routine
// that changed inside it, drawn by the renderer matching its language.
export function FileSection({
  index,
  file,
  showNumbers,
  zoom,
}: {
  index: number;
  file: PRFile;
  showNumbers: boolean;
  zoom: number;
}) {
  return (
    <section className="mr-section pr-file">
      <div className="mr-section-head">
        <div className="mr-section-title">
          <span className="mr-section-num">{index}.</span>
          <span className="pr-file-ico">
            <FileCode2 size={15} strokeWidth={1.8} />
          </span>
          <span className="pr-file-name">{file.name}</span>
          <span className="mr-section-count">
            {file.changes.length}{" "}
            {file.changes.length === 1 ? "routine" : "routines"}
          </span>
        </div>
      </div>
      <div className="pr-file-body" style={{ zoom: zoom / 100 }}>
        {file.changes.map((ch, i) => (
          <RoutineChangeBlock key={i} change={ch} showNumbers={showNumbers} />
        ))}
      </div>
    </section>
  );
}

// One routine's change within a file: a sub-header locating the routine, then
// the diff drawn by the matching renderer.
function RoutineChangeBlock({
  change,
  showNumbers,
}: {
  change: PRRoutineChange;
  showNumbers: boolean;
}) {
  return (
    <div className="pr-routine">
      <div className="pr-routine-head">
        <span className="pr-routine-name">
          {change.program ? `${change.program} / ` : ""}
          {change.routine}
        </span>
      </div>
      {change.kind === "ladder" && change.ladder ? (
        <div className="mr-ladderwrap">
          <RoutineLadderDiffView
            routine={change.ladder}
            showNumbers={showNumbers}
          />
        </div>
      ) : change.code ? (
        <CodeDiffBody diff={change.code} />
      ) : null}
    </div>
  );
}

// ---- Structured-text diff ----
const ST_KEYWORDS = new Set([
  "IF", "THEN", "ELSE", "ELSIF", "END_IF", "AND", "OR", "NOT", "TRUE", "FALSE",
  "RETURN", "FOR", "TO", "DO", "WHILE", "END_FOR", "END_WHILE", "CASE", "OF",
  "END_CASE", "XOR", "MOD",
]);

// Lightweight ST highlighter. Tokens wrapped in ⟦…⟧ are the changed value on
// this side (green on the right, red on the left); known keywords render in the
// accent colour; everything else is plain text.
export function highlightST(
  text: string,
  side: "left" | "right",
): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const changeCls = side === "right" ? "tok-add" : "tok-rem";
  const parts = text.split(/(⟦[^⟧]*⟧)/g);
  let key = 0;
  for (const part of parts) {
    if (!part) continue;
    if (part.startsWith("⟦") && part.endsWith("⟧")) {
      out.push(
        <span className={changeCls} key={key++}>
          {part.slice(1, -1)}
        </span>,
      );
      continue;
    }
    const toks = part.split(/(\b[A-Za-z_][A-Za-z0-9_]*\b)/g);
    for (const tok of toks) {
      if (!tok) continue;
      if (ST_KEYWORDS.has(tok)) {
        out.push(
          <span className="tok-kw" key={key++}>
            {tok}
          </span>,
        );
      } else {
        out.push(<span key={key++}>{tok}</span>);
      }
    }
  }
  return out;
}

// Structured-text diff: two aligned columns (.mr-sxs), dark side headers, and
// token highlighting, so both review pages' code diffs match.
export function CodeDiffBody({ diff }: { diff: MRCodeDiff }) {
  const rows = Math.max(diff.left.lines.length, diff.right.lines.length);
  const last = rows - 1;
  return (
    <div className="pr-codewrap">
      <div className="mr-sxs mr-sxs-code">
        <div className="sxs-head sxs-head-l">
          <span className="sxs-head-ver">{diff.left.ref}</span>
        </div>
        <div className="sxs-head sxs-gut" />
        <div className="sxs-head sxs-head-r">
          <span className="sxs-head-ver">{diff.right.ref}</span>
        </div>
        {Array.from({ length: rows }).map((_, i) => {
          const l = diff.left.lines[i];
          const r = diff.right.lines[i];
          const edge = i === last ? " sxs-last" : "";
          return (
            <div className="sxs-row" key={i} style={{ display: "contents" }}>
              <div className={`sxs-cell sxs-l${edge}`}>
                {l && (
                  <div className="cd-line">
                    <span className="cd-num">{l.ln}</span>
                    <span className="cd-code">{highlightST(l.text, "left")}</span>
                  </div>
                )}
              </div>
              <div className="sxs-gut" />
              <div className={`sxs-cell sxs-r${edge}`}>
                {r && (
                  <div className="cd-line">
                    <span className="cd-num">{r.ln}</span>
                    <span className="cd-code">{highlightST(r.text, "right")}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ZoomControl({
  zoom,
  onZoom,
}: {
  zoom: number;
  onZoom: (z: number) => void;
}) {
  return (
    <div className="zoom">
      <button
        className="zoom-btn"
        type="button"
        aria-label="Zoom out"
        onClick={() => onZoom(Math.max(50, zoom - 10))}
      >
        <Minus size={14} strokeWidth={2} />
      </button>
      <span className="zoom-val">{zoom}%</span>
      <button
        className="zoom-btn"
        type="button"
        aria-label="Zoom in"
        onClick={() => onZoom(Math.min(200, zoom + 10))}
      >
        <Plus size={14} strokeWidth={2} />
      </button>
    </div>
  );
}
