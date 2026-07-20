// The shared threaded discussion used by both review pages (commit and
// merge-request). The backend stores a FLAT comment list where each reply
// carries its TRUE parent id (a reply to a reply points at that reply, not the
// thread root). Rendering stays one visual level per thread: every reply sits
// flat under its root comment, and a reply whose parent is itself a reply gets
// a small quote of that parent — clicking it scrolls the parent into view.
import { useState } from "react";
import { CornerUpLeft } from "lucide-react";
import { errorText } from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { timeAgo } from "../lib/time";
import { initials } from "../lib/initials";

// The comment shape both pages map their backend rows onto.
export interface DiscussionComment {
  id: number;
  parentId: number | null;
  authorId?: number; // enables the "You" chip when known
  author: string; // display name
  at: string; // ISO
  body: string;
}

export function Discussion({
  comments,
  loading = false,
  loadError = null,
  posting,
  postError,
  onAdd,
}: {
  comments: DiscussionComment[];
  loading?: boolean;
  loadError?: unknown;
  posting: boolean;
  postError: unknown;
  onAdd: (body: string, parentId: number | null) => void;
}) {
  const { user } = useAuth();
  const [flashId, setFlashId] = useState<number | null>(null);

  const byId = new Map(comments.map((c) => [c.id, c]));
  // The thread a comment belongs to is its outermost ancestor.
  const rootOf = (c: DiscussionComment): number => {
    let cur = c;
    while (cur.parentId != null) {
      const p = byId.get(cur.parentId);
      if (!p) break;
      cur = p;
    }
    return cur.id;
  };
  const roots = comments.filter((c) => c.parentId == null);

  const jumpTo = (id: number) => {
    document
      .getElementById(`disc-comment-${id}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlashId(id);
    window.setTimeout(() => setFlashId((f) => (f === id ? null : f)), 1600);
  };

  return (
    <section className="mr-section">
      <div className="mr-section-head">
        <div className="mr-section-title">
          Discussion
          <span className="mr-section-count">{comments.length} comments</span>
        </div>
      </div>
      <div className="disc-list">
        {loading ? (
          <div className="rail-empty">Loading comments…</div>
        ) : loadError ? (
          <div className="rail-empty">
            {errorText(loadError, "Couldn't load the discussion.")}
          </div>
        ) : (
          <>
            {comments.length === 0 && (
              <div className="rail-empty">No comments yet.</div>
            )}
            {roots.map((c) => (
              <CommentThread
                key={c.id}
                comment={c}
                replies={comments.filter(
                  (r) => r.parentId != null && rootOf(r) === c.id,
                )}
                byId={byId}
                meId={user?.id}
                flashId={flashId}
                posting={posting}
                onJump={jumpTo}
                onReply={onAdd}
              />
            ))}
          </>
        )}
        {postError != null && (
          <div className="form-error">
            {errorText(postError, "Couldn't post the comment.")}
          </div>
        )}
        <DiscussionComposer
          placeholder="Add a comment…"
          submitLabel="Comment"
          busy={posting}
          onSubmit={(body) => onAdd(body, null)}
        />
      </div>
    </section>
  );
}

// One top-level comment with all of its thread's replies flat beneath it.
// The reply composer targets whichever comment's Reply button was clicked,
// so the stored parent id is the comment actually being answered.
function CommentThread({
  comment,
  replies,
  byId,
  meId,
  flashId,
  posting,
  onJump,
  onReply,
}: {
  comment: DiscussionComment;
  replies: DiscussionComment[];
  byId: Map<number, DiscussionComment>;
  meId?: number;
  flashId: number | null;
  posting: boolean;
  onJump: (id: number) => void;
  onReply: (body: string, parentId: number) => void;
}) {
  const [replyTo, setReplyTo] = useState<DiscussionComment | null>(null);
  return (
    <div className="disc-thread">
      <CommentItem
        comment={comment}
        meId={meId}
        flash={flashId === comment.id}
        onReplyClick={() =>
          setReplyTo((prev) => (prev?.id === comment.id ? null : comment))
        }
      />
      {(replies.length > 0 || replyTo) && (
        <div className="disc-replies">
          {replies.map((r) => (
            <CommentItem
              key={r.id}
              comment={r}
              meId={meId}
              flash={flashId === r.id}
              // Quote the direct parent only when it isn't the thread root —
              // a first-level reply already sits right under it.
              quoted={
                r.parentId !== comment.id
                  ? byId.get(r.parentId!)
                  : undefined
              }
              onJump={onJump}
              onReplyClick={() =>
                setReplyTo((prev) => (prev?.id === r.id ? null : r))
              }
            />
          ))}
          {replyTo && (
            <DiscussionComposer
              placeholder={`Reply to ${replyTo.author}…`}
              submitLabel="Reply"
              compact
              busy={posting}
              onSubmit={(body) => {
                onReply(body, replyTo.id);
                setReplyTo(null);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

const snippet = (s: string) => (s.length > 90 ? `${s.slice(0, 90)}…` : s);

function CommentItem({
  comment: c,
  meId,
  flash,
  quoted,
  onJump,
  onReplyClick,
}: {
  comment: DiscussionComment;
  meId?: number;
  flash?: boolean;
  quoted?: DiscussionComment;
  onJump?: (id: number) => void;
  onReplyClick: () => void;
}) {
  const isAuthor = meId != null && c.authorId === meId;
  return (
    <article
      className={`disc-item${flash ? " disc-flash" : ""}`}
      id={`disc-comment-${c.id}`}
    >
      <span className="disc-av">{initials(c.author)}</span>
      <div className="disc-main">
        <div className="disc-content">
          <div className="disc-top">
            <span className="disc-who">{c.author}</span>
            {isAuthor && <span className="disc-role">You</span>}
          </div>
          {quoted && (
            <button
              type="button"
              className="disc-quote"
              onClick={() => onJump?.(quoted.id)}
              title="Go to the reply this answers"
            >
              <CornerUpLeft size={12} strokeWidth={2} />
              <span className="disc-quote-who">{quoted.author}</span>
              <span className="disc-quote-snip">{snippet(quoted.body)}</span>
            </button>
          )}
          <p className="disc-body">{c.body}</p>
          <button type="button" className="link-btn disc-reply" onClick={onReplyClick}>
            Reply
          </button>
        </div>
        <div className="disc-aside">
          <div className="disc-aside-top">
            <span className="disc-time">{timeAgo(c.at)}</span>
          </div>
        </div>
      </div>
    </article>
  );
}

// Comment composer. Posts through the parent's callback; `busy` guards
// against double-submits while a post is in flight.
function DiscussionComposer({
  placeholder,
  submitLabel,
  compact,
  busy,
  onSubmit,
}: {
  placeholder: string;
  submitLabel: string;
  compact?: boolean;
  busy?: boolean;
  onSubmit: (body: string) => void;
}) {
  const { user } = useAuth();
  const [body, setBody] = useState("");
  const name = user?.name ?? "You";
  const canSubmit = body.trim().length > 0 && !busy;

  const submit = () => {
    if (!canSubmit) return;
    onSubmit(body.trim());
    setBody("");
  };

  return (
    <div className={`disc-composer${compact ? " compact" : ""}`}>
      <span className="disc-av">{initials(name)}</span>
      <div className="disc-composer-main">
        <textarea
          className={`textarea${compact ? "" : " tall"}`}
          placeholder={placeholder}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          autoFocus={compact}
        />
        <div className="disc-composer-actions">
          <button
            className="btn btn-primary btn-sm"
            type="button"
            disabled={!canSubmit}
            onClick={submit}
          >
            {submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
