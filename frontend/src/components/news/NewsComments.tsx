import { useState } from "react"
import {
  MessageSquare as ChatBubbleOutlineIcon,
  Edit2 as EditIcon,
  Trash2 as DeleteIcon,
  Send as SendIcon,
} from "lucide-react"
import { Button, Textarea } from "@/components/ui"

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
    <footer className="w-full max-w-4xl mt-(length:--space-12) border-t border-glass-border/(--opacity-soft) pt-(length:--space-10)">
      <div className="flex items-center gap-(length:--fluid-gap) mb-(length:--space-8)">
        <ChatBubbleOutlineIcon className="h-6 w-6 text-brand" size={24} />
        <h2 className="text-(length:--fs-h3) font-extrabold text-(--text-primary)">
          {t("news:sections.comments", { defaultValue: "Комментарии" })}
        </h2>
        <span className="px-2 py-0.5 rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) text-xs font-bold tabular-nums text-brand">
          {comments.length}
        </span>
      </div>

      <div className="flex flex-col gap-(--space-6) mb-(length:--space-10)">
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
                <span className="font-bold text-sm text-(--text-primary)">{comment.user_name}</span>
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
                        className="p-1.5 rounded-full hover:bg-(--bg-surface)/(--opacity-strong) text-(--text-secondary) hover:text-(--text-primary) transition-colors"
                        title={t("news:actions.editComment", { defaultValue: "Edit" })}
                      >
                        <EditIcon className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (
                            confirm(
                              t("news:dialogs.deleteComment.confirm", {
                                defaultValue: "Delete this comment?",
                              })
                            )
                          ) {
                            void deleteComment(comment.id)
                          }
                        }}
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
                <div className="flex flex-col gap-(--space-3) mt-(length:--space-1)">
                  <Textarea
                    value={editingCommentText}
                    onChange={(event) => setEditingCommentText(event.target.value)}
                    className="min-h-20 text-sm"
                    autoFocus
                  />
                  <div className="flex justify-end gap-(--space-2)">
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
                <p className="text-base leading-relaxed whitespace-pre-wrap text-(--text-primary)">
                  {comment.content}
                </p>
              )}
            </div>
          ))
        )}
      </div>

      {user && (
        <div className="flex flex-col gap-(--space-4)">
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
    </footer>
  )
}
