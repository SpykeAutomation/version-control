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
// surrounding card/footer so it can sit in a tab or on a branch page.
export function FilesTable({ files, slug }: { files: FileEntry[]; slug: string }) {
  return (
    <div className="dtable-scroll"><table className="dtable">
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>Description</th>
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
              <td className="muted-cell">{FILE_KIND_LABEL[file.kind]}</td>
              <td className="muted-cell">{file.description ?? "—"}</td>
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
