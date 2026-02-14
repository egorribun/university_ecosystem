import Dialog from "@/components/Dialog"
import { Button, ContentCard, Snackbar } from "@/components/ui"
import { SpotlightOverlay, useSpotlight } from "@/components/ui/Spotlight"
import { useLanguage } from "@/contexts/LanguageContext"
import { useNewsInteraction } from "@/hooks/useNewsInteraction"
import { cn } from "@/utils/cn"
import { sanitizeNewsText } from "@/utils/sanitize"
import { motion } from "framer-motion"
import { Trash2 as DeleteIcon } from "lucide-react"
import { FC, lazy, memo, Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import api from "../api/client"
import { useAuth } from "../contexts/AuthContext"
import NewsCardContent from "./news/NewsCardContent"
import NewsCardHero from "./news/NewsCardHero"

const NewsCardActions = lazy(() =>
  import("./news/NewsCardActions").then((m) => ({ default: m.NewsCardActions }))
)
const NewsCardEditDialog = lazy(() =>
  import("./news/NewsCardEditDialog").then((m) => ({ default: m.NewsCardEditDialog }))
)

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

// getMoscowDate removed, imported from @/utils/date

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

  const hoveringDisabled = editOpen

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      onMouseMove={spotlight.onMouseMove}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      whileHover={!hoveringDisabled ? { y: -4 } : undefined}
      className={cn("h-full outline-none", hoveringDisabled ? "cursor-default" : "cursor-pointer")}
    >
      <ContentCard
        hoverable={!hoveringDisabled}
        className={cn(
          "card-news group h-full",
          hoveringDisabled ? "cursor-default" : "card-interactive"
        )}
      >
        <SpotlightOverlay
          mouseX={spotlight.mouseX}
          mouseY={spotlight.mouseY}
          className="z-hide"
        />

        {user?.role === "admin" && (
          <ContentCard.Actions className="absolute right-2 top-2 z-surface">
            <Suspense fallback={null}>
              <NewsCardActions
                id={id}
                onEdit={openEdit}
                onDelete={openDeletePrompt}
                isDisabled={loading}
              />
            </Suspense>
          </ContentCard.Actions>
        )}

        <div
          className={cn(
            "group/content relative flex h-full flex-1 flex-col text-left",
            hoveringDisabled ? "opacity-100" : ""
          )}
        >
          <NewsCardHero
            image_url={image_url}
            title={localizedTitle}
            created_at={created_at}
          />

          <NewsCardContent
            id={id}
            title={localizedTitle}
            preview={sanitizedPreview}
            isLiked={isLiked}
            likesCount={likesCount}
            commentsCount={commentsCount}
            onToggleLike={toggleLike}
            hoveringDisabled={hoveringDisabled}
          />
        </div>

        <Suspense fallback={null}>
          <NewsCardEditDialog
            id={id}
            open={editOpen}
            onClose={closeEdit}
            initialData={editData}
            onSuccess={onChange}
          />
        </Suspense>

        <Dialog
          open={confirmDeleteOpen}
          onClose={closeDeletePrompt}
          title={t("news:dialogs.delete.title")}
          bodyClassName="space-y-4"
          footer={
            <>
              <Button
                variant="outline"
                onClick={closeDeletePrompt}
                disabled={loading}
                className="w-full sm:w-auto"
              >
                {t("common:buttons.cancel")}
              </Button>
              <Button
                onClick={() => {
                  void handleDelete()
                }}
                disabled={loading}
                loading={loading}
                className="w-full bg-error-bg text-error-text hover:bg-error-bg/(--opacity-heavy) sm:w-auto"
              >
                <DeleteIcon size={18} className="mr-1" />
                {t("common:buttons.delete")}
              </Button>
            </>
          }
        >
          <p className="text-input text-(--text-secondary)">
            {t("news:dialogs.delete.description")}
          </p>
        </Dialog>
        <Snackbar open={!!error} message={error} onClose={() => setError("")} />
      </ContentCard>
    </motion.article>
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
