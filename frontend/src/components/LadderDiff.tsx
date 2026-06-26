import {
  Fragment,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import type {
  ElementStatus,
  IRElement,
  IRRoutineLadderDiff,
  IRRungDiff,
  LadderDiffDoc,
} from "../api/diff";

// Draws a ladder diff straight from the engine IR. The IR is aligned by rung:
// each IRRungDiff is one row that spans both sides, so we render a two-column
// grid with one row per rung — left draws `before`, right draws `after`. This is
// the IR-faithful renderer and handles every element kind (contact, coil, box,
// branch, raw); it is separate from Ladder.tsx, which draws the older mock data.

// Instruction glyphs are small; the connecting wire is drawn by the rung OUTSIDE
// the glyph, so a change highlight hugs the instruction and the wires stay
// visible (and boxes sit on the same rail as contacts).
const GLYPH_H = 30;
const GMID = GLYPH_H / 2;

// --- SVG symbols ---------------------------------------------------------

// A normally-open or normally-closed contact, with short stubs to the chip edge.
function ContactSymbol({ form }: { form?: string | null }) {
  const closed = form === "nc";
  return (
    <svg className="el-symbol" width={34} height={GLYPH_H} aria-hidden="true">
      <line x1={0} y1={GMID} x2={12} y2={GMID} stroke="currentColor" strokeWidth={1.6} />
      <line x1={22} y1={GMID} x2={34} y2={GMID} stroke="currentColor" strokeWidth={1.6} />
      <line x1={12} y1={5} x2={12} y2={25} stroke="currentColor" strokeWidth={1.9} />
      <line x1={22} y1={5} x2={22} y2={25} stroke="currentColor" strokeWidth={1.9} />
      {closed && (
        <line x1={11} y1={26} x2={23} y2={4} stroke="currentColor" strokeWidth={1.9} />
      )}
    </svg>
  );
}

// An output coil. "otl" marks it latched (L), "otu" unlatched (U).
function CoilSymbol({ form }: { form?: string | null }) {
  const letter = form === "otl" ? "L" : form === "otu" ? "U" : null;
  return (
    <svg className="el-symbol" width={40} height={GLYPH_H} aria-hidden="true">
      <line x1={0} y1={GMID} x2={16} y2={GMID} stroke="currentColor" strokeWidth={1.6} />
      <line x1={24} y1={GMID} x2={40} y2={GMID} stroke="currentColor" strokeWidth={1.6} />
      <path d="M16 2 Q3 15 16 28" fill="none" stroke="currentColor" strokeWidth={1.9} />
      <path d="M24 2 Q37 15 24 28" fill="none" stroke="currentColor" strokeWidth={1.9} />
      {letter && (
        <text x={20} y={19} textAnchor="middle" fontSize={10} fontWeight={700} fill="currentColor">
          {letter}
        </text>
      )}
    </svg>
  );
}

// --- elements ------------------------------------------------------------

// Element-level status class. Drives the green/red/amber highlight in the CSS.
function elClass(el: IRElement): string {
  return `el-${el.status}`;
}

function branchLaneCount(el: IRElement): number {
  if (el.kind !== "branch") return 1;
  return Math.max(1, el.legs?.length ?? 0);
}

function maxBranchLaneCount(elements: IRElement[]): number {
  let max = 1;
  for (const el of elements) {
    if (el.kind === "branch") {
      max = Math.max(max, branchLaneCount(el));
      for (const leg of el.legs ?? []) {
        max = Math.max(max, maxBranchLaneCount(leg));
      }
    }
  }
  return max;
}

// The small corner badge on a changed element: + added, − removed, ~ modified.
function StatusBadge({ status }: { status: ElementStatus }) {
  if (status === "unchanged") return null;
  const sign = status === "added" ? "+" : status === "removed" ? "-" : "~";
  return <span className={`el-badge el-badge-${status}`}>{sign}</span>;
}

// Every instruction sits in a slot — a flexible wire, the chip, another flexible
// wire — so the wires fill the gaps and the rung reads as one continuous rail.
// `boundary` marks the first write: its leading wire takes up the rung's slack,
// pushing the writes to the right (and travels with it if the rung wraps).
function Slot({
  children,
  box,
  boundary,
}: {
  children: ReactNode;
  box?: boolean;
  boundary?: boolean;
}) {
  return (
    <div className={`el-slot${box ? " el-slot-box" : ""}${boundary ? " el-slot-boundary" : ""}`}>
      <span className="el-wire" aria-hidden="true" />
      {children}
      <span className="el-wire" aria-hidden="true" />
    </div>
  );
}

// A contact or coil: tag above, glyph on the rail, with wire stubs that carry
// the rail through the chip.
function ContactOrCoil({ el, boundary }: { el: IRElement; boundary?: boolean }) {
  return (
    <Slot boundary={boundary}>
      <ContactOrCoilChip el={el} />
    </Slot>
  );
}

function ContactOrCoilChip({ el }: { el: IRElement }) {
  const label = el.label ?? "";
  return (
    <div className={`el-chip ${elClass(el)}`}>
      <StatusBadge status={el.status} />
      <div className="el-tag" title={label}>
        {label}
      </div>
      <div className="el-wirerow">
        <span className="el-iwire" aria-hidden="true" />
        {el.kind === "contact" ? (
          <ContactSymbol form={el.form} />
        ) : (
          <CoilSymbol form={el.form} />
        )}
        <span className="el-iwire" aria-hidden="true" />
      </div>
    </div>
  );
}

// A box (instruction or AOI): a titled rectangle with one row per operand,
// sitting on the rail like an inline instruction.
function BoxElement({ el, boundary }: { el: IRElement; boundary?: boolean }) {
  return (
    <Slot box boundary={boundary}>
      <BoxChip el={el} />
    </Slot>
  );
}

function BoxChip({ el }: { el: IRElement }) {
  const operands = el.operands ?? [];
  return (
    <div className={`ladder-box ${elClass(el)}`}>
      <StatusBadge status={el.status} />
      <div className="box-title">{el.mnemonic ?? "?"}</div>
      {operands.length > 0 && (
        <div className="box-operands">
          {operands.map((op, i) => (
            <div
              key={i}
              className={`box-operand${op.changed ? " operand-changed" : ""}`}
            >
              <span className="operand-label">{op.label}</span>
              <span className="operand-value" title={op.value}>
                {op.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// A branch: parallel legs stacked vertically, joined on both ends. Legs hold
// their own slotted elements, so the rail continues through each leg.
function BranchElement({ el, boundary }: { el: IRElement; boundary?: boolean }) {
  return (
    <Slot boundary={boundary}>
      <BranchCore el={el} />
    </Slot>
  );
}

function BranchCore({ el }: { el: IRElement }) {
  const legs = el.legs ?? [];
  const lanes = branchLaneCount(el);
  const style = {
    "--branch-lanes": String(lanes),
    "--branch-drop": `${(lanes - 1) * 31}px`,
  } as CSSProperties;
  return (
    <div className={`ladder-branch ${elClass(el)}`} style={style}>
      <span className="branch-join branch-join-l" aria-hidden="true" />
      <div className="branch-legs">
        {legs.map((leg, i) => (
          <div className="branch-leg" key={i}>
            <span className="branch-wire" aria-hidden="true" />
            {leg.length === 0 ? (
              <span className="branch-pass" aria-hidden="true" />
            ) : (
              <span className="branch-leg-elements">
                {leg.map((child, j) => (
                  <Fragment key={j}>
                    {j > 0 && <span className="branch-mid-wire" aria-hidden="true" />}
                    <BareElement el={child} />
                  </Fragment>
                ))}
              </span>
            )}
            <span className="branch-wire" aria-hidden="true" />
          </div>
        ))}
      </div>
      <span className="branch-join branch-join-r" aria-hidden="true" />
    </div>
  );
}

// Anything the IR could not classify is shown verbatim in a monospace pill.
function RawElement({ el, boundary }: { el: IRElement; boundary?: boolean }) {
  return (
    <Slot boundary={boundary}>
      <span className={`ladder-raw ${elClass(el)}`}>{el.text ?? ""}</span>
    </Slot>
  );
}

function BareElement({ el }: { el: IRElement }) {
  switch (el.kind) {
    case "contact":
    case "coil":
      return <ContactOrCoilChip el={el} />;
    case "box":
      return <BoxChip el={el} />;
    case "branch":
      return <BranchCore el={el} />;
    case "raw":
      return <span className={`ladder-raw ${elClass(el)}`}>{el.text ?? ""}</span>;
    default:
      return <span className={`ladder-raw ${elClass(el)}`}>{el.text ?? ""}</span>;
  }
}

// Dispatch one IR element to the right drawing. Kept exhaustive on kind.
function Element({ el, boundary }: { el: IRElement; boundary?: boolean }) {
  switch (el.kind) {
    case "contact":
    case "coil":
      return <ContactOrCoil el={el} boundary={boundary} />;
    case "box":
      return <BoxElement el={el} boundary={boundary} />;
    case "branch":
      return <BranchElement el={el} boundary={boundary} />;
    case "raw":
      return <RawElement el={el} boundary={boundary} />;
    default:
      // Future kinds still render something rather than nothing.
      return <RawElement el={el} boundary={boundary} />;
  }
}

// --- rung lines ----------------------------------------------------------

// A continuation marker at a wrap point, in panel-relative coordinates.
type WrapMark = { x: number; y: number; dir: "in" | "out" };

// One rung drawn as a single wrapping line. The left rail leads the first row,
// the right rail closes the last, and the first write's leading wire takes up
// the slack (reads left, writes right). When the line wraps, it measures the
// rows and overlays continuation arrows — "out" at the right of a row that
// continues, "in" at the left of the row it continues onto — so the wire reads
// as one rung across the rows. Markers are absolute overlays, so they never
// shift the flow that produced them.
function RungNet({ elements }: { elements: IRElement[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [marks, setMarks] = useState<WrapMark[]>([]);
  const [fills, setFills] = useState<{ x: number; y: number; w: number }[]>([]);
  const [railR, setRailR] = useState<{ x: number; y: number } | null>(null);
  const firstWrite = elements.findIndex((e) => e.io === "output");

  useLayoutEffect(() => {
    const net = ref.current;
    if (!net) return;
    const measure = () => {
      const box = net.getBoundingClientRect();
      // Children on one flex row share a vertical centre (align-items: center),
      // so group by it; arrows ignore themselves.
      const rows = new Map<number, { left: number; right: number; y: number }>();
      for (const child of Array.from(net.children) as HTMLElement[]) {
        if (
          child.classList.contains("wrap-arrow") ||
          child.classList.contains("rung-fill") ||
          child.classList.contains("rung-rail-r")
        )
          continue;
        const b = child.getBoundingClientRect();
        if (b.width === 0 && b.height === 0) continue;
        const y = (b.top + b.bottom) / 2 - box.top;
        const key = Math.round(y / 4) * 4;
        const left = b.left - box.left;
        const right = b.right - box.left;
        const cur = rows.get(key);
        if (cur) {
          cur.left = Math.min(cur.left, left);
          cur.right = Math.max(cur.right, right);
        } else {
          rows.set(key, { left, right, y });
        }
      }
      const ordered = [...rows.values()].sort((a, b) => a.y - b.y);
      // Right edge of the rung-net content box, in the same panel-relative space
      // as row.left/right/y (rung-net has no horizontal padding, so the content
      // box right edge equals its width).
      const panelRight = box.width;
      const next: WrapMark[] = [];
      const nextFills: { x: number; y: number; w: number }[] = [];
      let nextRailR: { x: number; y: number } | null = null;
      ordered.forEach((row, i) => {
        const last = i === ordered.length - 1;
        // A row that continues: the wire runs to the panel's right edge (the
        // wrap point), so put the "out" chevron there and fill the gap to it.
        if (!last) next.push({ x: panelRight, y: row.y, dir: "out" });
        if (i > 0) next.push({ x: row.left, y: row.y, dir: "in" });
        // The right rail is out of flow now, so the last row also ends short of
        // the edge. Fill every row from its rightmost element to the panel's
        // right edge so the wire reaches the rail (last row) / wrap point.
        const w = panelRight - row.right;
        if (w > 1) nextFills.push({ x: row.right, y: row.y, w });
        // The right rail closes only the final row, at the panel's right edge.
        if (last) nextRailR = { x: panelRight, y: row.y };
      });
      setMarks((prev) =>
        JSON.stringify(prev) === JSON.stringify(next) ? prev : next,
      );
      setFills((prev) =>
        JSON.stringify(prev) === JSON.stringify(nextFills) ? prev : nextFills,
      );
      setRailR((prev) =>
        JSON.stringify(prev) === JSON.stringify(nextRailR) ? prev : nextRailR,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(net);
    return () => observer.disconnect();
  }, [elements]);

  return (
    <div className="rung-net" ref={ref}>
      <span className="rail rail-l" aria-hidden="true" />
      {elements.map((el, i) => (
        <Element key={i} el={el} boundary={i === firstWrite} />
      ))}
      {railR && (
        <span
          className="rung-rail-r"
          style={{ left: `${railR.x}px`, top: `${railR.y}px` }}
          aria-hidden="true"
        />
      )}
      {marks.map((m, i) => (
        <span
          key={`wrap-${i}`}
          className={`wrap-arrow wrap-${m.dir}`}
          style={{ left: `${m.x}px`, top: `${m.y}px` }}
          aria-hidden="true"
        />
      ))}
      {fills.map((f, i) => (
        <span
          key={`fill-${i}`}
          className="rung-fill"
          style={{ left: `${f.x}px`, top: `${f.y}px`, width: `${f.w}px` }}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}

// The status accent for one side of a rung. A wholly added/removed rung tints
// its whole row; a modified rung stays neutral (just an accent bar) and lets the
// changed *element* carry the colour, so you can see exactly what changed.
function rungAccent(status: IRRungDiff["status"], isBefore: boolean): string {
  if (status === "added") return isBefore ? "" : "lad-rung-add";
  if (status === "removed") return isBefore ? "lad-rung-rem" : "";
  if (status === "modified") return "lad-rung-mod";
  if (status === "comment_changed") return "lad-rung-cmt";
  return "";
}

// One rung as it appears in a single column (before or after). The side that a
// rung doesn't exist on (the old side of an added rung, the new side of a
// removed one) renders a striped placeholder so the two columns stay aligned.
function RungLine({
  rung,
  isBefore,
  showNumbers,
}: {
  rung: IRRungDiff;
  isBefore: boolean;
  showNumbers?: boolean;
}) {
  const elements = isBefore ? rung.before : rung.after;
  const num = isBefore ? rung.old_number : rung.new_number;
  const comment = isBefore ? rung.old_comment : rung.new_comment;
  const missing =
    (rung.status === "added" && isBefore) ||
    (rung.status === "removed" && !isBefore);
  const accent = rungAccent(rung.status, isBefore);
  const lanes = maxBranchLaneCount(elements);
  const style = { "--rung-branch-lanes": String(lanes) } as CSSProperties;

  return (
    <div
      className={`lad-rung ${lanes > 1 ? "lad-rung-branched" : ""} ${
        missing ? "lad-rung-empty" : accent
      }`}
      style={style}
    >
      {showNumbers &&
        (missing ? (
          <div className="rung-num rung-num-empty" />
        ) : (
          <div className="rung-num">{typeof num === "number" ? num + 1 : ""}</div>
        ))}
      {missing ? (
        <div className="lad-empty" />
      ) : (
        <div className="lad-rung-main">
          {comment && <div className="lad-rung-caption">{comment}</div>}
          {elements.length > 0 && <RungNet elements={elements} />}
        </div>
      )}
    </div>
  );
}

function LadderHeader({
  isBefore,
  label,
  count,
}: {
  isBefore: boolean;
  label?: string | null;
  count: number;
}) {
  return (
    <div className={`lad-col-head lad-col-head-${isBefore ? "before" : "after"}`}>
      <span className="lad-col-ver">{label ?? (isBefore ? "Before" : "After")}</span>
      <span className="lad-col-count">
        {count} {count === 1 ? "rung" : "rungs"}
      </span>
    </div>
  );
}

function RungDiffRow({
  rung,
  showNumbers,
}: {
  rung: IRRungDiff;
  showNumbers?: boolean;
}) {
  return (
    <div className="lad-row">
      <div className="lad-cell lad-cell-before">
        <RungLine rung={rung} isBefore showNumbers={showNumbers} />
      </div>
      <div className="lad-cell lad-cell-after">
        <RungLine rung={rung} isBefore={false} showNumbers={showNumbers} />
      </div>
    </div>
  );
}

// --- public components ---------------------------------------------------

// Draws one routine as a side-by-side diff card: a header with the routine name,
// then two aligned columns (before | after). Pure and presentational.
export function RoutineLadderDiffView({
  routine,
  showNumbers,
}: {
  routine: IRRoutineLadderDiff;
  showNumbers?: boolean;
}) {
  return (
    <section className="ladder-diff-card">
      <div className="ladder-diff-head">
        <LadderHeader isBefore label={routine.old_label} count={routine.rungs.length} />
        <LadderHeader
          isBefore={false}
          label={routine.new_label}
          count={routine.rungs.length}
        />
      </div>
      <div className="ladder-diff-body">
        {routine.rungs.map((rung, i) => (
          <RungDiffRow key={i} rung={rung} showNumbers={showNumbers} />
        ))}
      </div>
    </section>
  );
}

// Draws a routine in full as a single column (no before/after), for read-only
// viewing of an unchanged routine. Reuses the same per-rung rendering as the
// diff view; each rung shows its "after" side with neutral (unchanged) styling.
export function RoutineLadderFullView({
  routine,
  showNumbers,
}: {
  routine: IRRoutineLadderDiff;
  showNumbers?: boolean;
}) {
  return (
    <section className="ladder-full-card">
      <div className="lad-col-head">
        <span className="lad-col-ver">
          {routine.new_label ?? routine.old_label ?? "Current"}
        </span>
      </div>
      <div className="ladder-full-body">
        {routine.rungs.map((rung, i) => (
          <div className="ladfull-cell" key={i}>
            <RungLine rung={rung} isBefore={false} showNumbers={showNumbers} />
          </div>
        ))}
      </div>
    </section>
  );
}

// Thin helper: draw every routine in a whole diff document.
export function LadderDiffView({
  doc,
  showNumbers,
}: {
  doc: LadderDiffDoc;
  showNumbers?: boolean;
}) {
  return (
    <div className="ladder-diff-doc">
      {doc.routines.map((routine, i) => (
        <RoutineLadderDiffView
          key={i}
          routine={routine}
          showNumbers={showNumbers}
        />
      ))}
    </div>
  );
}
