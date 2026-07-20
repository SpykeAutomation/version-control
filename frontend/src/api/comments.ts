// Commit-page discussion comments (GET/POST /projects/{id}/commits/{sha}/
// comments). The backend returns a FLAT list in creation order; threading is
// client-side via parent_id, which is preserved at ANY depth — the UI renders
// one visual level per thread but uses the true parent to quote-link a reply
// to the reply it answered. Short shas are fine: the backend stores comments
// under the fully resolved sha, so short-ref posts and reads converge.
import { apiFetch } from "./client";
import { displayName, type UserBrief } from "./users";

export interface CommentApi {
  id: number;
  author: UserBrief;
  body: string;
  resolved: boolean;
  parent_id: number | null;
  created_at: string;
  edited_at: string | null;
}

export interface CommitComment {
  id: number;
  parentId: number | null;
  authorId: number;
  author: string; // display name
  at: string; // ISO
  body: string;
}

function mapComment(c: CommentApi): CommitComment {
  return {
    id: c.id,
    parentId: c.parent_id,
    authorId: c.author.id,
    author: displayName(c.author),
    at: c.created_at,
    body: c.body,
  };
}

export async function listCommitComments(
  projectId: number,
  sha: string,
): Promise<CommitComment[]> {
  const rows = await apiFetch<CommentApi[]>(
    `/projects/${projectId}/commits/${sha}/comments?limit=100`,
  );
  return rows.map(mapComment);
}

export async function addCommitComment(
  projectId: number,
  sha: string,
  input: { body: string; parentId?: number | null },
): Promise<CommitComment> {
  const row = await apiFetch<CommentApi>(
    `/projects/${projectId}/commits/${sha}/comments`,
    {
      method: "POST",
      json: {
        body: input.body,
        ...(input.parentId != null ? { parent_id: input.parentId } : {}),
      },
    },
  );
  return mapComment(row);
}
