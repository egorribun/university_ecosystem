import { useSpotlight } from "@/components/ui/Spotlight"
import { useLanguage } from "@/contexts/LanguageContext"
import { useNewsInteraction } from "@/hooks/useNewsInteraction"
import { useBookmarks } from "@/hooks/useBookmarks"
import { sanitizeNewsText } from "@/utils/sanitize"
import { localizeField } from "@/utils/localize"
import { inferNewsCategory } from "@/features/news/categories"
import { estimateReadingTime } from "@/utils/readingTime"
import { fetchNewsItem } from "@/api/news"
import { FC, memo, useCallback, useEffect, useMemo, useRef, useState, lazy } from "react"
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
  /** First card in grid — forwards LCP priority to SmartImage (Wave 113 PERF-113-01) */
  priority?: boolean
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
  priority,
}) => {
  const { user } = useAuth()
  const { t } = useTranslation(["news", "common"])
  const { language } = useLanguage()

  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [openEditContext, setOpenEditContext] = useState<string | null>(null)
  const editSourceRequestRef = useRef<AbortController | null>(null)
  const isMountedRef = useRef(false)
  const currentEditContext = JSON.stringify([id, language])

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
  const [editDialogData, setEditDialogData] = useState(editData)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      editSourceRequestRef.current?.abort()
    }
  }, [])

  useEffect(
    () => () => {
      editSourceRequestRef.current?.abort()
    },
    [id, language]
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
  const { isBookmarked, toggleBookmark } = useBookmarks()
  const handleToggleBookmark = useCallback(() => toggleBookmark(id), [id, toggleBookmark])

  const localizedTitle = useMemo(
    () => localizeField(title, title_en, language),
    [language, title, title_en]
  )

  const localizedContent = useMemo(
    () => localizeField(content, content_en, language),
    [language, content, content_en]
  )

  const category = useMemo(
    () => inferNewsCategory({ title, content, title_en, content_en }),
    [content, content_en, title, title_en]
  )
  const readingTime = useMemo(() => estimateReadingTime(localizedContent), [localizedContent])

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
      setError(t("common:errors.generic"))
    } finally {
      setLoading(false)
      setConfirmDeleteOpen(false)
    }
  }, [id, onChange, t])

  const openEdit = useCallback(async () => {
    setError("")
    if (language !== "en") {
      setEditDialogData(editData)
      setOpenEditContext(currentEditContext)
      setEditOpen(true)
      return
    }

    if (editSourceRequestRef.current && !editSourceRequestRef.current.signal.aborted) return
    const controller = new AbortController()
    editSourceRequestRef.current = controller
    setLoading(true)
    try {
      const response = await fetchNewsItem(id, { language: "ru", signal: controller.signal })
      if (
        controller.signal.aborted ||
        editSourceRequestRef.current !== controller ||
        !isMountedRef.current
      ) {
        return
      }
      if (response.status === 304) throw new Error("Russian source was not returned")
      setEditDialogData({
        title: response.data.title,
        content: response.data.content,
        title_en: response.data.title_en ?? "",
        content_en: response.data.content_en ?? "",
        image_url: response.data.image_url ?? "",
      })
      setOpenEditContext(currentEditContext)
      setEditOpen(true)
    } catch {
      if (!controller.signal.aborted && editSourceRequestRef.current === controller) {
        setError(t("common:errors.generic"))
      }
    } finally {
      if (editSourceRequestRef.current === controller) {
        editSourceRequestRef.current = null
        if (isMountedRef.current) setLoading(false)
      }
    }
  }, [currentEditContext, editData, id, language, t])
  const closeEdit = useCallback(() => {
    setEditOpen(false)
    setOpenEditContext(null)
  }, [])

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
      isBookmarked={isBookmarked(id)}
      isAdmin={user?.role === "admin"}
      loading={loading}
      error={error}
      hoveringDisabled={editOpen && openEditContext === currentEditContext}
      readingTime={readingTime}
      category={category}
      editOpen={editOpen && openEditContext === currentEditContext}
      confirmDeleteOpen={confirmDeleteOpen}
      editData={editDialogData}
      spotlight={spotlight}
      onToggleLike={toggleLike}
      onToggleBookmark={handleToggleBookmark}
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
      priority={priority}
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
  prev.onChange === next.onChange &&
  prev.priority === next.priority

// PERF-27-02-KEPT: custom areEqual comparator
export default memo(NewsCardComponent, areNewsCardPropsEqual)
