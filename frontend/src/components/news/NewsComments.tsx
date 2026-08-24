import { useState } from "react"
import { cn } from "@/utils/cn"
import {
  MessageSquare as CommentIcon,
  Edit2 as EditIcon,
  Trash2 as DeleteIcon,
  Send as SendIcon,
} from "lucide-react"
import { Button, Textarea, ConfirmDialog } from "@/components/ui"
import type { NewsComment } from "@/hooks/useNewsInteraction"
import type { User } from "@/types/User"

const COMMENT_MAX_LENGTH = 500

interface NewsCommentsProps {
  comments: NewsComment[]
  user?: Pick<User, "id" | "role"> | null
  isCommenting: boolean
  addComment: (content: string) => void
  updateComment: (id: string, content: string) => void
  deleteComment: (id: string) => void
  t: (key: string, options?: Record<string, unknown>) => string
  getMoscowDate: (date: string) => string
}

export function NewsComments({
  comments,
  user,
  isCommenting,
  addComment,
  updateComment,
  deleteComment,
  t,
  getMoscowDate,
}: NewsCommentsProps) {
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null)
  const [editingCommentText, setEditingCommentText] = useState("")
  const [commentText, setCommentText] = useState("")
  const [deleteConfirmationId, setDeleteConfirmationId] = useState<string | null>(null)

  const handlePostComment = () => {
    addComment(commentText)
    setCommentText("")
  }

  const handleUpdateComment = (id: string) => {
    updateComment(id, editingCommentText)
    setEditingCommentId(null)
  }

  return (
    <section
      aria-labelledby="comments-heading"
      className="w-full glass-layer-surface glass-noise rounded-2xl p-6 sm:p-8"
    >
      {/* ── Section header ── */}
      <div className="flex items-center gap-3 mb-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) text-brand">
          <CommentIcon size={20} />
        </div>
        <h2 id="comments-heading" className="text-xl sm:text-2xl font-extrabold text-text-primary">
          {t("news:sections.comments")}
        </h2>
        <span className="px-2.5 py-0.5 rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) text-xs font-bold tabular-nums text-brand">
          {comments.length}
        </span>
      </div>

      {/* ── Comments list ── */}
      <div className="flex flex-col gap-3 mb-8">
        {comments.length === 0 ? (
          <p className="text-(--text-secondary) italic py-6 text-center text-sm">
            {t("news:states.noComments")}
          </p>
        ) : (
          comments.map((comment) => (
            <div
              key={comment.id}
              className="flex flex-col gap-2 p-4 rounded-xl bg-(--bg-matte-list) border border-glass-border/(--opacity-soft) transition-colors hover:border-glass-border"
            >
              {/* Comment header */}
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold text-sm text-text-primary truncate">
                  {comment.user_name}
                </span>

                <div className="flex items-center gap-2 shrink-0">
                  <time className="text-xs text-(--text-secondary) uppercase font-semibold tracking-wide">
                    {getMoscowDate(comment.created_at)}
                  </time>

                  {/* Owner / admin actions */}
                  {(user?.id === comment.user_id || user?.role === "admin") && (
                    <div className="flex items-center gap-0.5">
                      <button
                        type="button"
                        onClick={() => {
                          setEditingCommentId(comment.id)
                          setEditingCommentText(comment.content)
                        }}
                        className="p-1.5 rounded-lg hover:bg-(--bg-surface)/(--opacity-strong) text-(--text-secondary) hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/(--opacity-medium)"
                        title={t("news:actions.editComment")}
                        aria-label={t("news:actions.editComment")}
                      >
                        <EditIcon size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteConfirmationId(comment.id)}
                        className="p-1.5 rounded-lg hover:bg-(--error-text)/(--opacity-subtle) text-(--error-text) transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--error-text)/(--opacity-medium)"
                        title={t("news:actions.deleteComment")}
                        aria-label={t("news:actions.deleteComment")}
                      >
                        <DeleteIcon size={14} />
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Comment body — inline edit or display */}
              {editingCommentId === comment.id ? (
                <div className="flex flex-col gap-3 mt-1">
                  <Textarea
                    value={editingCommentText}
                    onChange={(event) =>
                      setEditingCommentText(event.target.value.slice(0, COMMENT_MAX_LENGTH))
                    }
                    aria-label={t("news:form.editCommentAriaLabel")}
                    className="min-h-20 text-sm"
                    maxLength={COMMENT_MAX_LENGTH}
                    // eslint-disable-next-line jsx-a11y/no-autofocus
                    autoFocus
                  />
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={cn(
                        "text-[11px] tabular-nums transition-colors",
                        editingCommentText.length >= COMMENT_MAX_LENGTH * 0.95
                          ? "text-(--error-text) font-bold"
                          : editingCommentText.length >= COMMENT_MAX_LENGTH * 0.8
                            ? "text-warning-text font-semibold"
                            : "text-(--text-secondary)/(--opacity-medium)"
                      )}
                    >
                      {editingCommentText.length}/{COMMENT_MAX_LENGTH}
                    </span>
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="glass" size="sm" onClick={() => setEditingCommentId(null)}>
                      {t("common:buttons.cancel")}
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleUpdateComment(comment.id)}
                      disabled={!editingCommentText.trim()}
                    >
                      {t("common:buttons.save")}
                    </Button>
                  </div>
                </div>
              ) : (
                <p className="text-sm sm:text-base leading-relaxed whitespace-pre-wrap text-text-primary">
                  {comment.content}
                </p>
              )}
            </div>
          ))
        )}
      </div>

      {/* ── New comment form ── */}
      {user && (
        <div className="flex flex-col gap-4 p-4 rounded-xl bg-(--bg-matte-list) border border-glass-border/(--opacity-soft)">
          <Textarea
            value={commentText}
            onChange={(event) => setCommentText(event.target.value)}
            placeholder={t("news:form.commentPlaceholder")}
            aria-label={t("news:form.commentAriaLabel")}
            maxLength={COMMENT_MAX_LENGTH}
            className="min-h-24"
          />
          <div className="flex justify-end">
            <span
              className={cn(
                "text-[11px] tabular-nums transition-colors",
                commentText.length >= COMMENT_MAX_LENGTH * 0.95
                  ? "text-(--error-text) font-bold"
                  : commentText.length >= COMMENT_MAX_LENGTH * 0.8
                    ? "text-warning-text font-semibold"
                    : "text-(--text-secondary)/(--opacity-medium)"
              )}
            >
              {commentText.length}/{COMMENT_MAX_LENGTH}
            </span>
          </div>
          <div className="flex justify-end">
            <Button
              onClick={handlePostComment}
              disabled={!commentText.trim() || isCommenting}
              loading={isCommenting}
              leadingIcon={<SendIcon size={16} />}
            >
              {t("news:actions.postComment")}
            </Button>
          </div>
        </div>
      )}

      {/* ── Delete confirmation ── */}
      <ConfirmDialog
        open={deleteConfirmationId !== null}
        title={t("news:dialogs.deleteComment.title")}
        message={t("news:dialogs.deleteComment.description")}
        confirmText={t("common:buttons.delete")}
        cancelText={t("common:buttons.cancel")}
        variant="danger"
        onConfirm={() => {
          void deleteComment(deleteConfirmationId!)
          setDeleteConfirmationId(null)
        }}
        onCancel={() => setDeleteConfirmationId(null)}
      />
    </section>
  )
}
