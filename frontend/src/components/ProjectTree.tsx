// The project-organizer sidebar on the commit page: the full Studio 5000
// structure at the commit, with changed nodes badged. Clicking a routine asks
// the page to filter the ladder diff to just that routine; clicking any other
// changed node asks the page to focus its change-summary rows.
import { useEffect, useMemo, useState } from "react";
import {
  Box,
  ChevronDown,
  ChevronRight,
  Cpu,
  Database,
  FileCode2,
  Folder,
  FolderOpen,
  HardDrive,
  ListTree,
  Tag,
} from "lucide-react";
import type { TreeNode, TreeNodeKind } from "../api/tree";

export interface RoutineSelection {
  controller: string;
  program: string;
  routine: string;
  // The routine's language ("rll" | "st" | …), used by callers to pick the
  // matching diff when a routine has more than one kind of change.
  routineType?: string | null;
}

interface ProjectTreeProps {
  root: TreeNode;
  selected: RoutineSelection | null;
  onSelectRoutine: (sel: RoutineSelection) => void;
  onSelectEntity?: (node: TreeNode) => void;
  onClear: () => void;
}

// Default-open the root, its top-level folders, and every node on a path to a
// change (descendant_changed marks exactly those ancestors), so changed logic
// is visible on load and the rest stays collapsed.
function defaultExpanded(root: TreeNode): Set<string> {
  const open = new Set<string>();
  const walk = (node: TreeNode, depth: number) => {
    if (depth === 0 || (node.kind === "folder" && depth === 1) || node.descendant_changed) {
      open.add(node.key);
    }
    for (const child of node.children) walk(child, depth + 1);
  };
  walk(root, 0);
  return open;
}

const KIND_ICON: Record<TreeNodeKind, typeof Folder> = {
  controller: Cpu,
  folder: Folder,
  program: ListTree,
  routine: FileCode2,
  aoi: Box,
  datatype: Database,
  tag: Tag,
  module: HardDrive,
  task: ListTree,
};

export function ProjectTree({
  root,
  selected,
  onSelectRoutine,
  onSelectEntity,
  onClear,
}: ProjectTreeProps) {
  const initial = useMemo(() => defaultExpanded(root), [root]);
  const [expanded, setExpanded] = useState<Set<string>>(initial);
  // A new commit (new root) resets the open set to its changed paths.
  useEffect(() => setExpanded(initial), [initial]);

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const isSelected = (node: TreeNode) =>
    selected != null &&
    node.routine === selected.routine &&
    node.program === selected.program &&
    node.controller === selected.controller;

  const renderNode = (node: TreeNode, depth: number): React.ReactNode => {
    const hasChildren = node.children.length > 0;
    const open = expanded.has(node.key);
    const isRoutine = node.kind === "routine" && !!node.routine;

    const onClick = () => {
      if (node.kind === "controller") {
        onClear();
        toggle(node.key);
      } else if (isRoutine) {
        onSelectRoutine({
          controller: node.controller ?? "",
          program: node.program ?? "",
          routine: node.routine!,
          routineType: node.routine_type,
        });
      } else if (hasChildren) {
        toggle(node.key);
      } else {
        onSelectEntity?.(node);
      }
    };

    const Icon = node.kind === "folder" && open ? FolderOpen : KIND_ICON[node.kind];

    return (
      <div key={node.key}>
        <button
          type="button"
          className={`tree-row${isSelected(node) ? " tree-row-active" : ""}`}
          style={{ paddingLeft: 8 + depth * 14 }}
          onClick={onClick}
          title={node.label}
        >
          <span className="tree-toggle" aria-hidden>
            {hasChildren ? (
              open ? (
                <ChevronDown size={14} strokeWidth={1.9} />
              ) : (
                <ChevronRight size={14} strokeWidth={1.9} />
              )
            ) : null}
          </span>
          <span className={`tree-ico tree-ico-${node.kind}`}>
            <Icon size={15} strokeWidth={1.7} />
          </span>
          <span className="tree-label">{node.label}</span>
          {/* One small black dot marks a change: on a changed node, or on a
             collapsed container hiding a change below it. */}
          {node.status !== "unchanged" || (node.descendant_changed && !open) ? (
            <span className="tree-dot" />
          ) : null}
        </button>
        {hasChildren && open ? (
          <div className="tree-children">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        ) : null}
      </div>
    );
  };

  return <div className="project-tree">{renderNode(root, 0)}</div>;
}
