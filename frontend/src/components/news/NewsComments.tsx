import { useState } from "react"
import {
  MessageSquare as CommentIcon,
  Edit2 as EditIcon,
  Trash2 as DeleteIcon,
  Send as SendIcon,
} from "lucide-react"
import { Button, Textarea, ConfirmDialog } from "@/components/ui"

interface Comment {
  id: number
  user_id: string
  user_name: string
  content: string
  created_at: string
}

interface NewsCommentsProps {
  comments: Comment[]
  user?: { id: string; role: string } | null
  isCommenting: boolean
  addComment: (content: string) => void
  updateComment: (id: number, content: string) => void
  deleteComment: (id: number) => void
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
  const [editingCommentId, setEditingCommentId] = useState<number | null>(null)
  const [editingCommentText, setEditingCommentText] = useState("")
  const [commentText, setCommentText] = useState("")
  const [deleteConfirmationId, setDeleteConfirmationId] = useState<number | null>(null)

  const handlePostComment = () => {
    if (commentText.trim()) {
      addComment(commentText)
      setCommentText("")
    }
  }

  const handleUpdateComment = (id: number) => {
    if (editingCommentText.trim()) {
      updateComment(id, editingCommentText)
      setEditingCommentId(null)
    }
  }

  return (
    <footer className="w-full glass-layer-surface glass-noise rounded-2xl p-6 sm:p-8">
      {/* ── Section header ── */}
      <div className="flex items-center gap-3 mb-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) text-brand">
          <CommentIcon size={20} />
        </div>
        <h2 className="text-xl sm:text-2xl font-extrabold text-text-primary">
          {t("news:sections.comments", { defaultValue: "Comments" })}
        </h2>
        <span className="px-2.5 py-0.5 rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) text-xs font-bold tabular-nums text-brand">
          {comments.length}
        </span>
      </div>

      {/* ── Comments list ── */}
      <div className="flex flex-col gap-3 mb-8">
        {comments.length === 0 ? (
          <p className="text-(--text-secondary) italic py-6 text-center text-sm">
            {t("news:states.noComments", {
              defaultValue: "No comments yet. Be the first!",
            })}
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
                        title={t("news:actions.editComment", { defaultValue: "Edit" })}
                        aria-label={t("news:actions.editComment", { defaultValue: "Edit comment" })}
                      >
                        <EditIcon size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteConfirmationId(comment.id)}
                        className="p-1.5 rounded-lg hover:bg-(--error-text)/(--opacity-subtle) text-(--error-text) transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--error-text)/(--opacity-medium)"
                        title={t("news:actions.deleteComment", { defaultValue: "Delete" })}
                        aria-label={t("news:actions.deleteComment", { defaultValue: "Delete comment" })}
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
                    onChange={(event) => setEditingCommentText(event.target.value)}
                    className="min-h-20 text-sm"
                    // eslint-disable-next-line jsx-a11y/no-autofocus
                    autoFocus
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="glass"
                      size="sm"
                      onClick={() => setEditingCommentId(null)}
                    >
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
            placeholder={t("news:form.commentPlaceholder", {
              defaultValue: "Write something...",
            })}
            className="min-h-24"
          />
          <div className="flex justify-end">
            <Button
              onClick={handlePostComment}
              disabled={!commentText.trim() || isCommenting}
              loading={isCommenting}
              leadingIcon={<SendIcon size={16} />}
            >
              {t("news:actions.postComment", { defaultValue: "Submit" })}
            </Button>
          </div>
        </div>
      )}

      {/* ── Delete confirmation ── */}
      <ConfirmDialog
        open={deleteConfirmationId !== null}
        title={t("news:dialogs.deleteComment.title", { defaultValue: "Deleting comment" })}
        message={t("news:dialogs.deleteComment.confirm", {
          defaultValue:
            "Are you sure you want to delete this comment? This action cannot be undone.",
        })}
        confirmText={t("common:buttons.delete")}
        cancelText={t("common:buttons.cancel")}
        variant="danger"
        onConfirm={() => {
          if (deleteConfirmationId) {
            void deleteComment(deleteConfirmationId)
            setDeleteConfirmationId(null)
          }
        }}
        onCancel={() => setDeleteConfirmationId(null)}
      />
    </footer>
  )
}
