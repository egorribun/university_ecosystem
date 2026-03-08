import { useSpotlight } from "@/components/ui/Spotlight"
import { useLanguage } from "@/contexts/LanguageContext"
import { useNewsInteraction } from "@/hooks/useNewsInteraction"
import { sanitizeNewsText } from "@/utils/sanitize"
import { FC, memo, useCallback, useEffect, useMemo, useState, lazy } from "react"
import { useTranslation } from "react-i18next"
import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"

const NewsCardView = lazy(() => import("./NewsCardView").then((m) => ({ default: m.NewsCardView })))

export type NewsCardProps = {
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

const NewsCardComponent: FC<NewsCardProps> = ({
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
}) => {
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

  const spotlight = useSpotlight()

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

  const [sanitizedPreview, setSanitizedPreview] = useState("")

  useEffect(() => {
    let mounted = true
    void sanitizeNewsText(localizedContent).then((text) => {
      if (mounted) setSanitizedPreview(text)
    })
    return () => {
      mounted = false
    }
  }, [localizedContent])

  const handleDelete = useCallback(async () => {
    setLoading(true)
    try {
      await api.delete(`/news/${id}`)
      onChange?.()
    } catch (_e) {
      setError(t("common:errors.generic", { defaultValue: "Произошла ошибка" }))
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

  const handleEditSuccess = useCallback(() => {
    onChange?.()
  }, [onChange])

  return (
    <NewsCardView
      id={id}
      title={localizedTitle}
      created_at={created_at}
      image_url={image_url}
      previewText={sanitizedPreview}
      isLiked={isLiked}
      likesCount={likesCount}
      commentsCount={commentsCount}
      isAdmin={user?.role === "admin"}
      loading={loading}
      error={error}
      hoveringDisabled={editOpen}
      editOpen={editOpen}
      confirmDeleteOpen={confirmDeleteOpen}
      editData={editData}
      spotlight={spotlight}
      onToggleLike={toggleLike}
      onEditOpen={openEdit}
      onEditClose={closeEdit}
      onDeleteOpen={openDeletePrompt}
      onDeleteClose={closeDeletePrompt}
      onDeleteConfirm={() => void handleDelete()}
      onEditSuccess={handleEditSuccess}
      onErrorClose={closeError}
      t={{
        deleteTitle: t("news:dialogs.delete.title"),
        deleteDesc: t("news:dialogs.delete.description"),
        confirm: t("common:buttons.delete"),
        cancel: t("common:buttons.cancel"),
      }}
    />
  )
}

const areNewsCardPropsEqual = (prev: NewsCardProps, next: NewsCardProps) =>
  prev.id === next.id &&
  prev.title === next.title &&
  prev.title_en === next.title_en &&
  prev.content === next.content &&
  prev.content_en === next.content_en &&
  prev.created_at === next.created_at &&
  prev.image_url === next.image_url &&
  prev.onChange === next.onChange

export default memo(NewsCardComponent, areNewsCardPropsEqual)
