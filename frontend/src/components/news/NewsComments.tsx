import { useState } from "react"
import {
  MessageSquare as ChatBubbleOutlineIcon,
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
    <footer className="w-full max-w-4xl mt-12 border-t border-glass-border/(--opacity-soft) pt-10">
      <div className="flex items-center gap-(--fluid-gap) mb-8">
        <ChatBubbleOutlineIcon className="h-6 w-6 text-brand" size={24} />
        <h2 className="text-3xl font-extrabold text-text-primary">
          {t("news:sections.comments", { defaultValue: "Комментарии" })}
        </h2>
        <span className="px-2 py-0.5 rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) text-xs font-bold tabular-nums text-brand">
          {comments.length}
        </span>
      </div>

      <div className="flex flex-col gap-6 mb-10">
        {comments.length === 0 ? (
          <p className="text-(--text-secondary) italic py-4">
            {t("news:states.noComments", {
              defaultValue: "Пока нет ни одного комментария. Будьте первым!",
            })}
          </p>
        ) : (
          comments.map((comment) => (
            <div
              key={comment.id}
              className="flex flex-col gap-2 p-4 rounded-md bg-(--bg-surface)/(--opacity-dim) border border-glass-border/(--opacity-soft) shadow-sm"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-text-primary">{comment.user_name}</span>
                <div className="flex items-center gap-3">
                  <time className="text-xs text-(--text-secondary) uppercase font-semibold">
                    {getMoscowDate(comment.created_at)}
                  </time>
                  {(user?.id === comment.user_id || user?.role === "admin") && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          setEditingCommentId(comment.id)
                          setEditingCommentText(comment.content)
                        }}
                        className="p-1.5 rounded-full hover:bg-(--bg-surface)/(--opacity-strong) text-(--text-secondary) hover:text-text-primary transition-colors"
                        title={t("news:actions.editComment", { defaultValue: "Edit" })}
                      >
                        <EditIcon className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirmationId(comment.id)}
                        className="p-1.5 rounded-full hover:bg-(--error-text)/(--opacity-subtle) text-(--error-text) hover:text-(--error-text)/(--opacity-hover) transition-colors"
                        title={t("news:actions.deleteComment", { defaultValue: "Delete" })}
                      >
                        <DeleteIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
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
                    <Button variant="outline" size="sm" onClick={() => setEditingCommentId(null)}>
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
                <p className="text-base leading-relaxed whitespace-pre-wrap text-text-primary">
                  {comment.content}
                </p>
              )}
            </div>
          ))
        )}
      </div>

      {user && (
        <div className="flex flex-col gap-4">
          <Textarea
            value={commentText}
            onChange={(event) => setCommentText(event.target.value)}
            placeholder={t("news:form.commentPlaceholder", {
              defaultValue: "Напишите что-нибудь...",
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
              {t("news:actions.postComment", { defaultValue: "Отправить" })}
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleteConfirmationId !== null}
        title={t("news:dialogs.deleteComment.title", { defaultValue: "Deleting comment" })}
        message={t("news:dialogs.deleteComment.confirm", {
          defaultValue: "Are you sure you want to delete this comment? This action cannot be undone.",
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
