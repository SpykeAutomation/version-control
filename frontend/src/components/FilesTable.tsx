import { Link } from "react-router-dom";
import {
  Boxes,
  Braces,
  Cpu,
  FileCode2,
  FileSpreadsheet,
  FileText,
  Monitor,
  Tag,
} from "lucide-react";
import { FILE_KIND_LABEL, type FileEntry, type FileKind } from "../api/repository";
import { useL5xController } from "../api/queries";
import { timeAgo } from "../lib/time";

export const FILE_ICON: Record<FileKind, typeof Tag> = {
  controller: Cpu,
  program: Boxes,
  routine: FileCode2,
  tags: Tag,
  io: FileSpreadsheet,
  hmi: Monitor,
  document: FileText,
  udt: Braces,
};

export function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

// The repository file listing. Names link to the file view; callers supply the
// surrounding card/footer so it can sit in a tab or on a branch page. The Name
// column is the file's actual (upload) name; the Controller column is the
// controller ("PLC") identity read from inside the L5X — often the same
// string, since Studio 5000 defaults the export name to the controller name,
// but they are different things. `projectId`/`refName` key that lookup.
export function FilesTable({
  files,
  slug,
  projectId,
  refName,
}: {
  files: FileEntry[];
  slug: string;
  projectId?: number;
  refName?: string;
}) {
  return (
    <div className="dtable-scroll"><table className="dtable">
      <thead>
        <tr>
          <th>Name</th>
          <th>Controller</th>
          <th>Type</th>
          <th>Last modified</th>
          <th>Last modified by</th>
          <th>Size</th>
        </tr>
      </thead>
      <tbody>
        {files.map((file) => {
          const Icon = FILE_ICON[file.kind];
          return (
            <tr key={file.name}>
              <td>
                <Link
                  to={`/organization/${slug}/files/${encodeURIComponent(file.name)}`}
                  className="file-cell"
                >
                  <span className="file-kind">
                    <Icon size={16} strokeWidth={1.8} />
                  </span>
                  <span className="file-cell-name">{file.name}</span>
                </Link>
              </td>
              <td>
                {file.kind === "controller" && file.path ? (
                  <ControllerCell
                    projectId={projectId}
                    refName={refName}
                    path={file.path}
                  />
                ) : (
                  <span className="muted-cell">—</span>
                )}
              </td>
              <td className="muted-cell">{FILE_KIND_LABEL[file.kind]}</td>
              <td className="muted-cell">{timeAgo(file.modifiedAt)}</td>
              <td>
                <span className="author">
                  <span className="author-av">{initials(file.modifiedBy)}</span>
                  {file.modifiedBy}
                </span>
              </td>
              <td className="muted-cell">{file.size}</td>
            </tr>
          );
        })}
      </tbody>
    </table></div>
  );
}

// The controller name (and processor/firmware, when known) inside one L5X
// file, fetched lazily per row and cached by (project, ref, path).
function ControllerCell({
  projectId,
  refName,
  path,
}: {
  projectId?: number;
  refName?: string;
  path: string;
}) {
  const q = useL5xController(projectId, refName, path);
  if (q.isPending) return <span className="muted-cell">…</span>;
  if (q.error || !q.data) return <span className="muted-cell">—</span>;
  const c = q.data;
  const firmware =
    c.major_rev != null ? `v${c.major_rev}.${c.minor_rev ?? 0}` : "";
  const sub = [c.processor_type, firmware].filter(Boolean).join(" · ");
  return (
    <span className="ctrl-cell">
      <span className="ctrl-cell-name">{c.name}</span>
      {sub && <span className="ctrl-cell-sub">{sub}</span>}
    </span>
  );
}
