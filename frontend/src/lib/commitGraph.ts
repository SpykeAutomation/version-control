// Builds the commit-graph model for the repo Overview's Tree view by walking
// parent pointers (the commits endpoint returns `parents`, first parent
// first), so the topology is exact:
//   - the trunk is the default branch's FIRST-parent chain;
//   - each trunk merge commit opens a side lane: its second parent starts the
//     merged branch's chain, walked until it rejoins something already drawn
//     (the fork point). This resurrects branches that were merged and then
//     DELETED — their commits stay reachable through the merge — named via
//     the merged pull ("Merge pull request #N" → source branch);
//   - live branches walk from their tips the same way; one already fully
//     drawn by a merge lane (merged-but-kept) isn't drawn twice.
// Chains that leave the loaded window (50 commits per list) end dangling and
// draw as a dashed tail instead of guessing.
import type { Commit } from "../api/repository";
import type { ChangeRequestSummary } from "../api/mergeRequest";

export interface GraphDot {
  sha: string;
  shortSha: string;
  title: string;
  author: string;
  at: string; // ISO
  laneKey: string;
  branch: string; // display name (lane's)
  lane: number; // 0 = trunk; +/-N = side lanes
  row: number; // 0 = newest (top)
  // Set on a trunk dot that is a merge commit: the branch it merged in.
  mergeOf?: string;
}

export interface GraphLane {
  key: string; // unique (a branch can merge more than once)
  branch: string; // display / click name
  lane: number;
  isDefault: boolean;
  // The branch ref still exists — its line and chip are clickable.
  live: boolean;
  colorIndex: number; // -1 = trunk (neutral ink); else palette slot
  dots: GraphDot[]; // newest first
  // Where the chain re-attached: the row/lane of the commit it forked from.
  forkRow?: number;
  forkLane?: number;
  // Chain left the loaded window — draw a dashed tail instead of a fork.
  forkDangling?: boolean;
  // Trunk row of the merge commit this lane converged into, if any.
  mergeRow?: number;
}

export interface CommitGraph {
  dots: GraphDot[];
  lanes: GraphLane[]; // trunk first
  rowCount: number;
  minLane: number;
  maxLane: number;
  truncated: boolean;
}

const MERGE_RE = /^Merge pull request #(\d+)\b/;
const PAGE_LIMIT = 50; // backend default page size for /commits

// Stable palette slot for a branch name, so colors survive reloads and new
// branches don't repaint existing ones. (A future per-branch setting on the
// backend can replace this.) Similar names hash to consecutive values
// ("patch-1", "patch-2", …), so the hash walks the palette with a coprime
// stride — siblings land on well-separated hues instead of neighbors.
export function branchColorIndex(name: string, paletteSize: number): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return (h * 3) % paletteSize;
}

interface Chain {
  key: string;
  branch: string;
  live: boolean;
  isDefault: boolean;
  commits: Commit[]; // newest first
  forkSha?: string; // commit (on an earlier-built chain) it forked from
  dangling: boolean;
  mergeSha?: string; // trunk merge commit it converged into
}

export function buildCommitGraph(
  defaultBranch: string,
  branches: { name: string }[],
  commitsByBranch: Record<string, Commit[] | null>,
  mergedPulls: ChangeRequestSummary[],
  paletteSize: number,
): CommitGraph {
  // Every loaded commit, by sha — the per-branch lists overlap heavily.
  const byId = new Map<string, Commit>();
  for (const list of Object.values(commitsByBranch)) {
    for (const c of list ?? []) if (!byId.has(c.sha)) byId.set(c.sha, c);
  }
  const liveNames = new Set(branches.map((b) => b.name));
  const pullByNumber = new Map(mergedPulls.map((p) => [p.number, p]));

  const assigned = new Map<string, string>(); // sha -> chain key
  const chains: Chain[] = [];

  // Walk the first-parent chain from `startSha`, claiming commits for `key`,
  // until the chain reaches an already-claimed commit (the fork point), the
  // root, or a commit outside the loaded window (dangling).
  function walk(startSha: string, key: string) {
    const commits: Commit[] = [];
    let sha: string | undefined = startSha;
    for (;;) {
      if (!sha) return { commits, forkSha: undefined, dangling: false }; // root
      if (assigned.has(sha)) return { commits, forkSha: sha, dangling: false };
      const c = byId.get(sha);
      if (!c) return { commits, forkSha: undefined, dangling: true };
      commits.push(c);
      assigned.set(sha, key);
      sha = c.parents?.[0];
    }
  }

  // 1. Trunk.
  const trunkTip = commitsByBranch[defaultBranch]?.[0];
  if (!trunkTip) {
    return { dots: [], lanes: [], rowCount: 0, minLane: 0, maxLane: 0, truncated: false };
  }
  const trunkWalk = walk(trunkTip.sha, defaultBranch);
  chains.push({
    key: defaultBranch,
    branch: defaultBranch,
    live: true,
    isDefault: true,
    commits: trunkWalk.commits,
    dangling: trunkWalk.dangling,
  });

  // 2. Side lanes opened by trunk merge commits (covers merged-and-kept AND
  // merged-and-deleted branches alike).
  const mergeName = (c: Commit): string => {
    const m = MERGE_RE.exec(c.message);
    const pull = m ? pullByNumber.get(parseInt(m[1], 10)) : undefined;
    return pull?.sourceBranch ?? `merge ${c.sha.slice(0, 7)}`;
  };
  for (const trunkCommit of trunkWalk.commits) {
    const extraParents = (trunkCommit.parents ?? []).slice(1);
    for (const p of extraParents) {
      const key = `merge:${trunkCommit.sha}:${p}`;
      const w = walk(p, key);
      if (w.commits.length === 0) continue; // second parent already drawn
      const name = mergeName(trunkCommit);
      chains.push({
        key,
        branch: name,
        live: liveNames.has(name),
        isDefault: false,
        commits: w.commits,
        forkSha: w.forkSha,
        dangling: w.dangling,
        mergeSha: trunkCommit.sha,
      });
    }
  }

  // 3. Live branches with work of their own (unmerged, or new commits after
  // a merge). A branch fully drawn by step 2 walks zero commits and is
  // skipped rather than duplicated.
  const featureTips = branches
    .filter((b) => b.name !== defaultBranch)
    .map((b) => ({ name: b.name, tip: commitsByBranch[b.name]?.[0] }))
    .filter((b): b is { name: string; tip: Commit } => b.tip != null)
    .sort((a, b) => Date.parse(b.tip.at) - Date.parse(a.tip.at));
  for (const { name, tip } of featureTips) {
    const w = walk(tip.sha, name);
    if (w.commits.length === 0) continue;
    chains.push({
      key: name,
      branch: name,
      live: true,
      isDefault: false,
      commits: w.commits,
      forkSha: w.forkSha,
      dangling: w.dangling,
    });
  }

  // Rows: every drawn commit, newest first; ties keep the trunk on top.
  const drawn = chains.flatMap((ch) =>
    ch.commits.map((c) => ({ c, isTrunk: ch.isDefault })),
  );
  drawn.sort((a, b) => {
    const t = Date.parse(b.c.at) - Date.parse(a.c.at);
    if (t !== 0) return t;
    return (a.isTrunk ? 0 : 1) - (b.isTrunk ? 0 : 1);
  });
  const rowBySha = new Map(drawn.map((d, i) => [d.c.sha, i]));

  // Lane numbers: trunk 0, side chains alternate by tip recency.
  const side = chains.filter((ch) => !ch.isDefault);
  side.sort(
    (a, b) => Date.parse(b.commits[0].at) - Date.parse(a.commits[0].at),
  );
  const laneByKey = new Map<string, number>([[defaultBranch, 0]]);
  side.forEach((ch, i) => {
    const step = Math.floor(i / 2) + 1;
    laneByKey.set(ch.key, i % 2 === 0 ? step : -step);
  });

  // Assemble.
  const mergeOfBySha = new Map<string, string>();
  for (const ch of chains) {
    if (ch.mergeSha) mergeOfBySha.set(ch.mergeSha, ch.branch);
  }
  const dots: GraphDot[] = [];
  const lanes: GraphLane[] = [];
  for (const ch of chains) {
    const lane = laneByKey.get(ch.key)!;
    const laneGraphDots: GraphDot[] = ch.commits.map((c) => ({
      sha: c.sha,
      shortSha: c.sha.slice(0, 7),
      title: c.message,
      author: c.author,
      at: c.at,
      laneKey: ch.key,
      branch: ch.branch,
      lane,
      row: rowBySha.get(c.sha)!,
      mergeOf: mergeOfBySha.get(c.sha),
    }));
    dots.push(...laneGraphDots);
    lanes.push({
      key: ch.key,
      branch: ch.branch,
      lane,
      isDefault: ch.isDefault,
      live: ch.live,
      colorIndex: ch.isDefault ? -1 : branchColorIndex(ch.branch, paletteSize),
      dots: laneGraphDots,
      forkRow: ch.forkSha != null ? rowBySha.get(ch.forkSha) : undefined,
      forkLane:
        ch.forkSha != null
          ? laneByKey.get(assigned.get(ch.forkSha)!)
          : undefined,
      forkDangling: ch.dangling,
      mergeRow: ch.mergeSha != null ? rowBySha.get(ch.mergeSha) : undefined,
    });
  }
  lanes.sort((a, b) => (a.isDefault ? -1 : b.isDefault ? 1 : a.lane - b.lane));

  const laneValues = [...laneByKey.values()];
  return {
    dots,
    lanes,
    rowCount: drawn.length,
    minLane: Math.min(...laneValues),
    maxLane: Math.max(...laneValues),
    truncated:
      chains.some((ch) => ch.dangling) ||
      Object.values(commitsByBranch).some(
        (l) => (l?.length ?? 0) >= PAGE_LIMIT,
      ),
  };
}
