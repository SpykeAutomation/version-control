import type { LadderElement, Rung } from "../api/compare";

// Renders a single ladder rung as a power-railed row of instructions. Each
// instruction is drawn as a crisp SVG symbol (contact, coil, timer) with its
// tag above and address below — the vernacular of PLC logic, not source code.

const CELL_W = 84;
const CELL_H = 46;
const MID = CELL_H / 2;

function Symbol({ kind }: { kind: LadderElement["kind"] }) {
  // Wire runs along the vertical middle; the symbol sits centred.
  const wire = (x1: number, x2: number) => (
    <line x1={x1} y1={MID} x2={x2} y2={MID} stroke="currentColor" strokeWidth={1.6} />
  );
  switch (kind) {
    case "no": // normally-open contact  ─┤ ├─
      return (
        <>
          {wire(0, 34)}
          {wire(50, CELL_W)}
          <line x1={34} y1={12} x2={34} y2={34} stroke="currentColor" strokeWidth={1.8} />
          <line x1={50} y1={12} x2={50} y2={34} stroke="currentColor" strokeWidth={1.8} />
        </>
      );
    case "nc": // normally-closed contact  ─┤/├─
      return (
        <>
          {wire(0, 34)}
          {wire(50, CELL_W)}
          <line x1={34} y1={12} x2={34} y2={34} stroke="currentColor" strokeWidth={1.8} />
          <line x1={50} y1={12} x2={50} y2={34} stroke="currentColor" strokeWidth={1.8} />
          <line x1={33} y1={35} x2={51} y2={11} stroke="currentColor" strokeWidth={1.8} />
        </>
      );
    case "coil": // output coil  ─( )─
    case "coil-set":
      return (
        <>
          {wire(0, 30)}
          {wire(54, CELL_W)}
          <path d="M34 12 Q26 23 34 34" fill="none" stroke="currentColor" strokeWidth={1.8} />
          <path d="M50 12 Q58 23 50 34" fill="none" stroke="currentColor" strokeWidth={1.8} />
          {kind === "coil-set" && (
            <text x={42} y={26} textAnchor="middle" fontSize={10} fontWeight={600} fill="currentColor">
              S
            </text>
          )}
        </>
      );
    case "timer":
    case "counter":
      return (
        <>
          {wire(0, 22)}
          {wire(62, CELL_W)}
          <rect x={22} y={9} width={40} height={28} rx={4} fill="none" stroke="currentColor" strokeWidth={1.6} />
          <text x={42} y={27} textAnchor="middle" fontSize={11} fontWeight={600} fill="currentColor">
            {kind === "timer" ? "TON" : "CTU"}
          </text>
        </>
      );
  }
}

function Element({ el, showHighlight }: { el: LadderElement; showHighlight: boolean }) {
  const state = showHighlight ? el.state ?? "unchanged" : "unchanged";
  return (
    <div className={`ladder-el el-${state}`}>
      <div className="el-tag" title={el.tag}>
        {el.tag}
      </div>
      <svg className="el-symbol" width={CELL_W} height={CELL_H} aria-hidden="true">
        <Symbol kind={el.kind} />
      </svg>
      <div className="el-addr">{el.address}</div>
    </div>
  );
}

interface RungViewProps {
  rung: Rung;
  showNumbers: boolean;
  showHighlight: boolean;
}

export function RungView({ rung, showNumbers, showHighlight }: RungViewProps) {
  const stateCls = showHighlight ? `rung-${rung.state}` : "rung-unchanged";
  return (
    <div className={`rung ${stateCls}`}>
      {showNumbers && <div className="rung-num">{rung.number}</div>}
      <div className="rung-net">
        <span className="rail rail-l" aria-hidden="true" />
        <div className="rung-els">
          {rung.elements.map((el, i) => (
            <Element key={i} el={el} showHighlight={showHighlight} />
          ))}
        </div>
        <span className="rail rail-r" aria-hidden="true" />
      </div>
    </div>
  );
}
