import { useCallback, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import api from "../../api/client"
import { useAuth } from "../../contexts/AuthContext"
import { useLanguage } from "../../contexts/LanguageContext"
import { useNewsInteraction } from "../../hooks/useNewsInteraction"
import { NewsCardView } from "./NewsCardView"

export type NewsCardContainerProps = {
  id: string
  title: string
  content: string
  title_en?: string | null
  content_en?: string | null
  created_at: string
  image_url?: string
  likes_count?: number
  comments_count?: number
  is_liked?: boolean
  onChange?: () => void
}

export const NewsCardContainer = ({
  id,
  title,
  content,
  title_en,
  content_en,
  created_at,
  image_url,
  likes_count: initialLikes = 0,
  comments_count: initialComments = 0,
  is_liked: initialIsLiked = false,
  onChange,
}: NewsCardContainerProps) => {
  const { user } = useAuth()
  const { t } = useTranslation(["news", "common"])
  const { language } = useLanguage()

  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const editData = useMemo(
    () => ({
      title,
      content,
      title_en: title_en ?? "",
      content_en: content_en ?? "",
      image_url: image_url || "",
    }),
    [title, content, title_en, content_en, image_url]
  )

  const { interactions, toggleLike } = useNewsInteraction(id, {
    initialData: {
      likes_count: initialLikes,
      comments_count: initialComments,
      is_liked: initialIsLiked,
    },
  })
  const likesCount = interactions?.likes_count ?? initialLikes
  const isLiked = interactions?.is_liked ?? initialIsLiked
  const commentsCount = interactions?.comments_count ?? initialComments


  const localizedTitle = useMemo(() => {
    const english = title_en ?? ""
    if (language === "en" && english.trim()) return english
    return title || english
  }, [language, title, title_en])

  const localizedContent = useMemo(() => {
    const english = content_en ?? ""
    if (language === "en" && english.trim()) return english
    return content || english
  }, [language, content, content_en])

  const handleDelete = useCallback(async () => {
    setLoading(true)
    try {
      await api.delete(`/news/${id}`)
      onChange?.()
    } catch (_e) {
      setError(t("common:errors.generic"))
    } finally {
      setLoading(false)
      setConfirmDeleteOpen(false)
    }
  }, [id, onChange, t])

  const openEdit = useCallback(() => setEditOpen(true), [])
  const closeEdit = useCallback(() => setEditOpen(false), [])

  const openDeletePrompt = useCallback(() => setConfirmDeleteOpen(true), [])
  const closeDeletePrompt = useCallback(() => setConfirmDeleteOpen(false), [])
  const closeError = useCallback(() => setError(""), [])

  return (
    <NewsCardView
      id={id}
      title={localizedTitle}
      contentRaw={localizedContent}
      created_at={created_at}
      image_url={image_url}
      isLiked={isLiked}
      likesCount={likesCount}
      commentsCount={commentsCount}
      onToggleLike={toggleLike}
      isAdmin={user?.role === "admin"}
      // Edit Dialog Props
      editOpen={editOpen}
      onOpenEdit={openEdit}
      onCloseEdit={closeEdit}
      editData={editData}
      onEditSuccess={onChange}
      // Delete Dialog Props
      confirmDeleteOpen={confirmDeleteOpen}
      onOpenDelete={openDeletePrompt}
      onCloseDelete={closeDeletePrompt}
      onConfirmDelete={handleDelete}
      // Status
      loading={loading}
      error={error}
      onErrorClose={closeError}
    />
  )
}
