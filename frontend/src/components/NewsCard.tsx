import { FC, memo, useState, useEffect, useCallback, useMemo, lazy, Suspense } from "react"
import { motion } from "framer-motion"
import {
  MoreVertical as MoreVertIcon,
  Pencil as EditIcon,
  Trash2 as DeleteIcon,
  Camera as PhotoCamera,
  ArrowUpRight as ArrowOutwardIcon,
  FileText as ArticleIcon,
  Heart as FavoriteIcon,
  MessageCircle as ChatBubbleOutlineIcon,
  Cloud,
} from "lucide-react"
import { useNewsInteraction } from "@/hooks/useNewsInteraction"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import api from "../api/client"
import { useNavigate } from "react-router-dom"
import dayjs from "dayjs"
import SmartImage from "@/components/SmartImage"
import { cn } from "@/utils/cn"
import { sanitizeNewsText } from "@/utils/sanitize"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { useSpotlight, SpotlightOverlay } from "@/components/ui/Spotlight"
import { getMoscowDate } from "@/utils/date"
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
  const navigate = useNavigate()
  const { t } = useTranslation(["news", "common"])
  const { language } = useLanguage()
  const isOnline = useOnlineStatus()

  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [cardImageReady, setCardImageReady] = useState(!image_url)

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

  const menuId = `news-card-menu-${id}`
  const menuButtonId = `${menuId}-button`

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

  const sanitizedPreview = useMemo(() => sanitizeNewsText(localizedContent), [localizedContent])
  const createdAtIso = useMemo(
    () => (created_at ? dayjs(created_at).toISOString() : ""),
    [created_at]
  )
  const createdAtLabel = useMemo(() => (created_at ? getMoscowDate(created_at) : ""), [created_at])
  const cardImageUrl = useMemo(() => image_url || "", [image_url])

  useEffect(() => {
    setCardImageReady(!cardImageUrl)
  }, [cardImageUrl])

  const handleCardImageReady = useCallback(() => setCardImageReady(true), [])

  const handleDelete = useCallback(async () => {
    setLoading(true)
    try {
      await api.delete(`/news/${id}`)
      onChange && onChange()
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setConfirmDeleteOpen(false)
    }
  }, [id, onChange])

  const openEdit = useCallback(() => setEditOpen(true), [])
  const closeEdit = useCallback(() => setEditOpen(false), [])

  const openDeletePrompt = useCallback(() => setConfirmDeleteOpen(true), [])
  const closeDeletePrompt = useCallback(() => setConfirmDeleteOpen(false), [])

  const handleCardClick = useCallback(() => {
    if (editOpen) return
    navigate(`/news/${id}`)
  }, [editOpen, id, navigate])

  const hoveringDisabled = editOpen

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "card-glass group relative flex flex-col transition-shadow duration-300 ease-out h-(--news-card-h-mobile) md:h-(--news-card-h-desktop) w-full transform-gpu",
        hoveringDisabled
          ? "cursor-default"
          : "cursor-pointer hover:shadow-glass-strong active:scale-[0.985]"
      )}
      style={{ width: "100%" }}
      onMouseMove={spotlight.onMouseMove}
    >
      <SpotlightOverlay mouseX={spotlight.mouseX} mouseY={spotlight.mouseY} className="z-(--z-hide)" />

      {user?.role === "admin" && (
        <Suspense fallback={null}>
          <NewsCardActions
            id={id}
            onEdit={openEdit}
            onDelete={openDeletePrompt}
            isDisabled={loading}
          />
        </Suspense>
      )}

      <div
        role="button"
        tabIndex={0}
        onClick={handleCardClick}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            handleCardClick()
          }
        }}
        className={cn(
          "group/button relative flex h-full flex-1 flex-col text-left focus-visible:outline-none",
          hoveringDisabled ? "cursor-default opacity-100" : "cursor-pointer"
        )}
      >
        <div className="relative w-full h-(--news-hero-h) md:h-(--news-hero-h-md) shrink-0 overflow-hidden border-b border-glass-border bg-linear-to-br from-brand/10 to-brand/5">
          <div
            className={cn(
              "absolute inset-0 animate-pulse bg-input-mix transition-opacity duration-300",
              cardImageReady ? "opacity-0" : "opacity-100"
            )}
            aria-hidden
          />
          {cardImageUrl ? (
            <>
              <SmartImage
                srcRaw={cardImageUrl}
                alt={
                  localizedTitle
                    ? t("news:alt.hero", { title: localizedTitle })
                    : t("news:alt.heroFallback")
                }
                sizes="(min-width: 1200px) 640px, (min-width: 900px) 520px, 100vw"
                className="absolute inset-0 h-full w-full object-cover transition duration-700 ease-out"
                onLoad={handleCardImageReady}
                onError={handleCardImageReady}
              />
              <div
                className="pointer-events-none absolute inset-0 z-(--z-decor) transition-opacity duration-300 group-hover:opacity-0 bg-linear-to-t from-black/90 via-black/40 to-transparent opacity-80"
                aria-hidden
              />
            </>
          ) : (
            <span className="relative z-(--z-deep) flex h-full w-full items-center justify-center overflow-hidden rounded-full">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand/40 opacity-40"></span>
              <ArticleIcon className="h-12 w-12" fontSize="large" />
            </span>
          )}
          {createdAtIso ? (
            <time
              dateTime={createdAtIso}
              className="absolute bottom-3 left-3 z-(--z-decor) rounded-full bg-black/60 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white/90 transition duration-300 ease-out group-hover/button:-translate-y-0.5 group-hover/button:bg-black/70"
            >
              {createdAtLabel}
            </time>
          ) : null}
          {!isOnline && (
            <div className="absolute top-3 left-3 z-(--z-decor) flex items-center gap-1 rounded-full bg-warning-bg/90 px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-wider text-warning-text shadow-surface backdrop-blur-sm">
              <Cloud size={12} />
              <span>{t("common:statuses.cached", { defaultValue: "Кэш" })}</span>
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-2 p-fluid-card-p transition duration-300 ease-out group-hover:-translate-y-px group-focus-visible/button:-translate-y-px md:gap-3">
          <h3 className="truncate text-[clamp(1.07rem,3vw,1.18rem)] font-semibold">
            {localizedTitle}
          </h3>

          <p className="min-h-(--space-12) text-sm text-(--text-secondary) line-clamp-2 md:min-h-(--space-18) md:line-clamp-3">
            {sanitizedPreview}
          </p>

          <div className="flex items-center gap-4 mt-1 border-t border-glass-border pt-3">
            <motion.button
              type="button"
              whileTap={{ scale: 0.85 }}
              onClick={(e) => {
                e.stopPropagation()
                toggleLike()
              }}
              className={cn(
                "flex items-center gap-1.5 transition-colors duration-200",
                isLiked ? "text-error-text" : "text-(--text-secondary) hover:text-error-text/80"
              )}
            >
              <div className="relative">
                {isLiked ? (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 400, damping: 15 }}
                  >
                    <FavoriteIcon size={18} fill={isLiked ? "currentColor" : "none"} />
                  </motion.div>
                ) : (
                  <FavoriteIcon size={18} />
                )}
              </div>
              <span className="text-xs font-bold tabular-nums">{likesCount}</span>
            </motion.button>

            <div className="flex items-center gap-1.5 text-(--text-secondary)">
              <ChatBubbleOutlineIcon size={18} />
              <span className="text-xs font-bold tabular-nums">{commentsCount}</span>
            </div>
          </div>

          <div className="mt-auto flex items-center gap-2 pt-2 text-(--primary-main)">
            <span className="translate-y-1 text-sm font-semibold tracking-wide opacity-0 transition duration-300 ease-out group-focus-visible/button:translate-y-0 group-focus-visible/button:opacity-100 group-hover:translate-y-0 group-hover:opacity-100">
              {t("common:cta.learnMore", { defaultValue: "Подробнее" })}
            </span>
            <ArrowOutwardIcon
              size={16}
              className="translate-x-0 text-(--primary-main) opacity-0 transition duration-300 ease-out group-focus-visible/button:translate-x-1 group-focus-visible/button:opacity-100 group-hover:translate-x-1 group-hover:opacity-100"
            />
          </div>
        </div>
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
              className="w-full bg-error-bg text-error-text hover:bg-error-bg/80 sm:w-auto"
            >
              <DeleteIcon size={18} className="mr-1" />
              {t("common:buttons.delete")}
            </Button>
          </>
        }
      >
        <p className="text-[0.98rem] text-(--text-secondary)">
          {t("news:dialogs.delete.description")}
        </p>
      </Dialog>
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





