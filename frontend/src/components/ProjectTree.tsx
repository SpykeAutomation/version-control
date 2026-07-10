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
  // Key of the entity node whose detail panel is open, for row highlighting.
  selectedEntityKey?: string | null;
  onSelectRoutine: (sel: RoutineSelection) => void;
  onSelectEntity?: (node: TreeNode) => void;
  onClear: () => void;
}

// Folders that open a detail panel when clicked (grids over the whole
// category); every other folder is a pure container and just toggles.
const PANEL_FOLDERS = new Set(["folder:tags", "folder:io"]);

// Whether clicking this node opens a detail panel (AOI parameters, UDT member
// table, tag grid, module table, AOI routine content) rather than only
// expanding it. Routine nodes without ladder identity are AOI routines — their
// content comes from the AOI section, so they select as entities too.
function hasDetailPanel(node: TreeNode): boolean {
  switch (node.kind) {
    case "aoi":
    case "datatype":
    case "tag":
    case "module":
      return true;
    case "routine":
      return !node.routine;
    case "folder":
      return PANEL_FOLDERS.has(node.key);
    default:
      return false;
  }
}

// Default-open only the root, so the project's first level is visible but
// collapsed — the reader expands the paths they care about.
function defaultExpanded(root: TreeNode): Set<string> {
  return new Set([root.key]);
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
  selectedEntityKey,
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
  // Expand only — selecting a panel node opens it without ever collapsing it
  // (the chevron handles collapse).
  const expand = (key: string) =>
    setExpanded((prev) => (prev.has(key) ? prev : new Set(prev).add(key)));

  const isSelected = (node: TreeNode) =>
    selected != null
      ? node.routine === selected.routine &&
        node.program === selected.program &&
        node.controller === selected.controller
      : selectedEntityKey != null && node.key === selectedEntityKey;

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
      } else if (hasDetailPanel(node)) {
        onSelectEntity?.(node);
        if (hasChildren) expand(node.key);
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
          role="treeitem"
          aria-expanded={hasChildren ? open : undefined}
          aria-selected={isSelected(node)}
          className={`tree-row${isSelected(node) ? " tree-row-active" : ""}`}
          style={{ paddingLeft: 8 + depth * 14 }}
          onClick={onClick}
          title={node.label}
        >
          <span
            className="tree-toggle"
            aria-hidden
            // The chevron is its own click target so panel nodes (which select
            // on row click) can still be collapsed.
            onClick={
              hasChildren
                ? (e) => {
                    e.stopPropagation();
                    toggle(node.key);
                  }
                : undefined
            }
          >
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
          <div className="tree-children" role="group">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="project-tree" role="tree">
      {renderNode(root, 0)}
    </div>
  );
}
