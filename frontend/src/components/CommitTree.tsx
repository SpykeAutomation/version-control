// The repo Overview's Tree view: the commit graph as a growing tree — the
// default branch is the trunk (newest at the top), feature branches sprout to
// the sides in their own color, and merged work converges back into the
// trunk. Dots are commits (hover for sha + title, click to open); clicking a
// branch's line opens the Files tab at that branch.
//
// Colors: categorical, from a fixed 8-slot palette validated against the app
// surface (dataviz skill; CVD-safe, labels provide the contrast relief).
// Assignment is a stable hash of the branch name — reloads and new branches
// don't repaint existing ones. The trunk wears the neutral ink instead.
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GitBranch } from "lucide-react";
import {
  errorText,
  useAllBranchCommits,
  useMergedPulls,
} from "../api/queries";
import {
  buildCommitGraph,
  type CommitGraph,
  type GraphDot,
  type GraphLane,
} from "../lib/commitGraph";
import { timeAgo } from "../lib/time";

const PALETTE = [
  "#2a78d6", // blue
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
  "#e87ba4", // magenta
  "#eb6834", // orange
];
const TRUNK_COLOR = "#32302c"; // neutral ink — the trunk is structure

const ROW_H = 36;
const LANE_W = 44;
const PAD_Y = 26;
const DOT_R = 5;

const laneColor = (l: GraphLane) =>
  l.colorIndex < 0 ? TRUNK_COLOR : PALETTE[l.colorIndex % PALETTE.length];

export function CommitTree({
  slug,
  projectId,
  defaultBranch,
  branches,
}: {
  slug: string;
  projectId?: number;
  defaultBranch: string;
  branches: { name: string }[];
}) {
  const names = branches.map((b) => b.name);
  const commitsQ = useAllBranchCommits(projectId, names);
  const pullsQ = useMergedPulls(projectId);

  const graph: CommitGraph | null = useMemo(() => {
    if (commitsQ.isPending || pullsQ.isPending) return null;
    return buildCommitGraph(
      defaultBranch,
      branches,
      commitsQ.byBranch,
      pullsQ.data ?? [],
      PALETTE.length,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commitsQ.isPending, commitsQ.byBranch, pullsQ.data, defaultBranch]);

  if (commitsQ.isPending || pullsQ.isPending) {
    return <div className="panel-msg">Growing the tree…</div>;
  }
  const err = commitsQ.error ?? pullsQ.error;
  if (err) {
    return (
      <div className="panel-msg error">
        {errorText(err, "Couldn't load the commit graph.")}
      </div>
    );
  }
  if (!graph || graph.rowCount === 0) {
    return <div className="panel-msg">No commits yet.</div>;
  }
  return <TreeSvg graph={graph} slug={slug} />;
}

// y of a row (row 0 = newest = top; the tree grows upward out of history).
const rowY = (row: number) => PAD_Y + row * ROW_H;

function TreeSvg({ graph, slug }: { graph: CommitGraph; slug: string }) {
  const navigate = useNavigate();
  const [hover, setHover] = useState<{ dot: GraphDot; x: number; y: number } | null>(
    null,
  );

  // Lane x positions: trunk centered, sprouts to either side. The side
  // margins leave room for the branch-name chips that hang off the tips.
  const LABEL_PAD = 170;
  const laneSpan = graph.maxLane - graph.minLane;
  const width = laneSpan * LANE_W + 2 * LABEL_PAD;
  const laneX = (lane: number) => (lane - graph.minLane) * LANE_W + LABEL_PAD;
  const trunkX = laneX(0);
  const height = rowY(graph.rowCount - 1) + PAD_Y + (graph.truncated ? 14 : 0);

  const goCommit = (d: GraphDot) =>
    navigate(`/organization/${slug}/commit/${d.sha}`);
  const goBranch = (branch: string) =>
    navigate(`/organization/${slug}?tab=Files&branch=${encodeURIComponent(branch)}`);

  return (
    <div className="ct-card">
      <div className="ct-scroll">
        <div className="ct-canvas" style={{ width, height }}>
          <svg width={width} height={height} role="img" aria-label="Commit tree">
            {graph.lanes.map((lane) => (
              <LanePaths
                key={lane.key}
                lane={lane}
                laneX={laneX}
                trunkX={trunkX}
                bottomY={height - 6}
                onLineClick={lane.live ? () => goBranch(lane.branch) : undefined}
              />
            ))}
            {graph.dots.map((d) => {
              const lane = graph.lanes.find((l) => l.key === d.laneKey)!;
              const color = laneColor(lane);
              return (
                <g key={d.sha}>
                  {d.mergeOf && (
                    <circle
                      cx={laneX(d.lane)}
                      cy={rowY(d.row)}
                      r={DOT_R + 3.5}
                      fill="none"
                      stroke={color}
                      strokeWidth={1.4}
                      opacity={0.5}
                    />
                  )}
                  <circle
                    cx={laneX(d.lane)}
                    cy={rowY(d.row)}
                    r={DOT_R}
                    fill={color}
                    stroke="#fbfaf7"
                    strokeWidth={2}
                  />
                  {/* oversized invisible hit target */}
                  <circle
                    cx={laneX(d.lane)}
                    cy={rowY(d.row)}
                    r={12}
                    fill="transparent"
                    className="ct-dot-hit"
                    onClick={() => goCommit(d)}
                    onMouseEnter={() =>
                      setHover({ dot: d, x: laneX(d.lane), y: rowY(d.row) })
                    }
                    onMouseLeave={() => setHover(null)}
                  />
                </g>
              );
            })}
          </svg>

          {/* branch name chips at each lane's tip — the visible labels that
              carry identity (contrast relief for the lighter hues) */}
          {graph.lanes.map((lane) => {
            const tip = lane.dots[0];
            const onRight = lane.lane >= 0;
            const color = laneColor(lane);
            return (
              <button
                key={lane.key}
                type="button"
                className={`ct-branch-label${lane.live ? "" : " ct-label-gone"}`}
                style={{
                  top: rowY(tip.row) - 11,
                  ...(onRight
                    ? { left: laneX(lane.lane) + 14 }
                    : { right: width - laneX(lane.lane) + 14 }),
                  borderColor: color,
                  color,
                }}
                onClick={lane.live ? () => goBranch(lane.branch) : undefined}
                title={
                  lane.live
                    ? `Open ${lane.branch}`
                    : `${lane.branch} was deleted after merging`
                }
              >
                <GitBranch size={11} strokeWidth={2.2} />
                {lane.branch}
              </button>
            );
          })}

          {hover && (
            <div
              className="ct-tooltip"
              style={{
                left: Math.min(hover.x + 16, width - 10),
                // Flip below the dot near the top edge, else the scroll
                // container clips the popup away.
                ...(hover.y > 96
                  ? { top: hover.y - 10, transform: "translateY(-100%)" }
                  : { top: hover.y + 14 }),
              }}
            >
              <div className="ct-tooltip-title">{hover.dot.title}</div>
              <div className="ct-tooltip-top">
                <span className="ct-tooltip-sha">{hover.dot.shortSha}</span>
                <span className="ct-tooltip-when">{timeAgo(hover.dot.at)}</span>
              </div>
              <div className="ct-tooltip-meta">
                {hover.dot.author}
                {hover.dot.mergeOf ? ` · merged ${hover.dot.mergeOf}` : ""}
              </div>
            </div>
          )}
        </div>
      </div>
      {graph.truncated && (
        <p className="ct-note">
          Showing the latest 50 commits per branch — older history isn't drawn.
          Branches that were merged and then deleted appear only as their merge
          commit (ringed dot) on the trunk.
        </p>
      )}
    </div>
  );
}

// One branch's geometry: the vertical line through its dots, the sprout curve
// down to the commit it forked from (usually on the trunk, but a branch can
// fork off another side lane), and the merge curve up into the trunk. A wide
// transparent twin of the path is the click/hover target (live branches only).
function LanePaths({
  lane,
  laneX,
  trunkX,
  bottomY,
  onLineClick,
}: {
  lane: GraphLane;
  laneX: (lane: number) => number;
  trunkX: number;
  bottomY: number;
  onLineClick?: () => void;
}) {
  const x = laneX(lane.lane);
  const color = laneColor(lane);
  const tipY = rowY(lane.dots[0].row);
  const lastY = rowY(lane.dots[lane.dots.length - 1].row);

  const parts: string[] = [`M ${x} ${tipY} L ${x} ${lastY}`];
  if (lane.isDefault) {
    // Trunk fades out at the bottom toward older, unloaded history.
    parts.push(`M ${x} ${lastY} L ${x} ${bottomY}`);
  } else if (lane.forkRow != null) {
    const fx = laneX(lane.forkLane ?? 0);
    const fy = rowY(lane.forkRow);
    parts.push(`M ${x} ${lastY} C ${x} ${lastY + ROW_H}, ${fx} ${fy - ROW_H}, ${fx} ${fy}`);
  } else if (lane.forkDangling) {
    parts.push(`M ${x} ${lastY} L ${x} ${bottomY}`);
  }
  if (lane.mergeRow != null) {
    const my = rowY(lane.mergeRow);
    parts.push(`M ${x} ${tipY} C ${x} ${tipY - ROW_H}, ${trunkX} ${my + ROW_H}, ${trunkX} ${my}`);
  }
  const d = parts.join(" ");

  return (
    <g className="ct-lane">
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeDasharray={lane.forkDangling ? "4 4" : undefined}
        className="ct-lane-line"
      />
      <path
        d={d}
        fill="none"
        stroke="transparent"
        strokeWidth={14}
        className={onLineClick ? "ct-lane-hit" : undefined}
        onClick={onLineClick}
      >
        <title>
          {onLineClick
            ? `Open ${lane.branch}`
            : `${lane.branch} (deleted after merging)`}
        </title>
      </path>
    </g>
  );
}
