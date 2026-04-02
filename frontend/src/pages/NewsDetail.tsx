import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import {
  ArrowLeft as ArrowBackIcon,
  Bookmark as BookmarkIcon,
  BookmarkCheck as BookmarkCheckIcon,
  Edit2 as EditIcon,
  Trash2 as DeleteIcon,
  Camera as PhotoCamera,
  Share2 as ShareIcon,
  Copy as CopyIcon,
  Heart as HeartIcon,
  Clock,
  Calendar,
} from "lucide-react"
import {
  Alert,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
} from "@/components/settings"
import { useNewsInteraction } from "@/hooks/useNewsInteraction"
import { useShare } from "@/hooks/useShare"
import { formatDate, toDate } from "@/utils/date"
import { deleteNews, fetchNewsItem, updateNews, uploadNewsImage, type NewsItem } from "@/api/news"

import { SEO } from "@/components/ui/SEO"
import SmartImage from "@/components/media/SmartImage"
import { Button, Input, Textarea, ConfirmDialog, Skeleton } from "@/components/ui"
import { NewsComments } from "@/components/news/NewsComments"
import { RelatedNews } from "@/components/news/RelatedNews"
import { NewsBackdrop } from "@/components/news/NewsBackdrop"
import { useBookmarks } from "@/hooks/useBookmarks"
import { useRelatedNews } from "@/hooks/useRelatedNews"
import { useArticleNavigation } from "@/hooks/useArticleNavigation"
import { useSwipe } from "@/hooks/useSwipe"
import { inferCategory } from "@/features/news/categories"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { TIMEOUTS } from "@/config/timeouts"
import useMediaQuery from "@/hooks/useMediaQuery"

/* ── Shared styles ── */
const iconBtnClass =
  "inline-flex h-10 w-10 items-center justify-center rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) text-(--text-secondary) shadow-sm transition hover:text-text-primary hover:shadow-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/(--opacity-medium)"

/* ── Form field helper ── */
type FieldProps = {
  label: ReactNode
  htmlFor: string
  children: ReactNode
  required?: boolean
}

function Field({ label, htmlFor, children, required = false }: FieldProps) {
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={htmlFor}
        className="text-sm font-semibold tracking-wide text-(--text-secondary)"
      >
        {label}
        {required && <span className="ml-1 text-(--error-text)">*</span>}
      </label>
      {children}
    </div>
  )
}

/* ── Data fetcher ── */
async function fetchNews(id: string): Promise<NewsItem> {
  const response = await fetchNewsItem(id)
  if (response.status === 304) throw new Error("Not modified")
  if (!response.data) throw new Error("Item not found")
  return response.data
}

const getMoscowDate = (dateStr: string) =>
  formatDate(dateStr, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Europe/Moscow",
  })

/* ══════════════════════════════════════════════════════════
   NEWS DETAIL PAGE
   ══════════════════════════════════════════════════════════ */
export default function NewsDetail() {
  const { id = "" } = useParams({ strict: false })
  const navigate = useNavigate()
  const { user } = useAuth()
  const { t } = useTranslation(["news", "common"])
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  const isNarrow = useMediaQuery("(max-width: 768px)")
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  /* ── Bookmarks ── */
  const { isBookmarked, toggleBookmark } = useBookmarks()
  const bookmarked = isBookmarked(id)
  const handleToggleBookmark = useCallback(() => toggleBookmark(id), [id, toggleBookmark])

  /* ── Article navigation (prev/next) ── */
  const { prevId, nextId, prevTitle, nextTitle } = useArticleNavigation(id)

  const goToArticle = useCallback(
    (articleId: string | null) => {
      if (articleId) void navigate({ to: "/news/$id", params: { id: articleId } })
    },
    [navigate]
  )

  const swipeHandlers = useSwipe({
    onSwipeLeft: () => goToArticle(nextId),
    onSwipeRight: () => goToArticle(prevId),
    threshold: 48,
    timeout: 500,
  })

  /* ── State ── */
  const [editOpen, setEditOpen] = useState(false)
  const [editData, setEditData] = useState({
    title: "",
    content: "",
    title_en: "",
    content_en: "",
    image_url: "",
  })
  const [saving, setSaving] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [snackbar, setSnackbar] = useState("")
  const [heroRatio, setHeroRatio] = useState<number | null>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const editTitleRef = useRef<HTMLInputElement>(null)

  /* ── Queries ── */
  const { data: newsItem } = useQuery<NewsItem>({ queryKey: ["news", id, language] })

  const {
    sharing,
    shareDialogOpen,
    setShareDialogOpen,
    copyingLink,
    copiedLink,
    shareOptions,
    handleShare,
    handleCopyLink,
  } = useShare({
    title: newsItem?.title || "",
    onNotify: (msg) => setSnackbar(msg),
    translations: {
      shareSuccess: t("news:notifications.shareSuccess"),
      shareError: t("news:notifications.shareError"),
      linkCopied: t("news:notifications.linkCopied"),
      pageTitle: t("news:pageTitle"),
      telegram: t("news:shareDialog.options.telegram"),
      whatsapp: t("news:shareDialog.options.whatsapp"),
      email: t("news:shareDialog.options.email"),
    },
  })

  const { interactions, toggleLike, addComment, isCommenting, updateComment, deleteComment } =
    useNewsInteraction(id, {
      initialData: newsItem
        ? {
            likes_count: newsItem.likes_count,
            comments_count: newsItem.comments_count,
            is_liked: newsItem.is_liked,
          }
        : undefined,
    })
  const isLiked = interactions?.is_liked ?? false
  const likesCount = interactions?.likes_count ?? 0
  const comments = interactions?.comments ?? []

  /* ── Hero image aspect ratio detection ── */
  const handleHeroLoad = useCallback<React.ReactEventHandler<HTMLImageElement>>((event) => {
    const img = event.currentTarget
    const w = img.naturalWidth || 0
    const h = img.naturalHeight || 0
    if (w && h) setHeroRatio(w / h)
  }, [])

  const heroFrame = useMemo(() => {
    if (!heroRatio || !Number.isFinite(heroRatio) || heroRatio <= 0) {
      return {
        container: "h-(--h-hero-sm) min-h-80 max-h-(--layout-max-modal)",
        image: "object-cover",
        imageStyle: { objectPosition: "50% 40%" },
        backdrop: "bg-(--bg-surface)/(--opacity-dim)",
      }
    }
    const r = Math.min(Math.max(heroRatio, 0.35), 4)
    if (r < 0.82)
      return {
        container: "min-h-(--min-h-hero-lg) max-h-(--h-hero-max-portrait) aspect-3/4",
        image: "object-contain object-center",
        imageStyle: { objectPosition: "center" },
        backdrop: "bg-black/(--opacity-soft)",
      }
    if (r < 1.18)
      return {
        container: "min-h-(--min-h-hero-md) max-h-(--h-hero-max-square) aspect-5/4",
        image: "object-cover",
        imageStyle: { objectPosition: "50% 38%" },
        backdrop: "bg-(--bg-surface)/(--opacity-dim)",
      }
    if (r > 2.6)
      return {
        container: "min-h-(--min-h-hero-xs) max-h-(--h-hero-md) aspect-21/9",
        image: "object-cover",
        imageStyle: { objectPosition: "50% 46%" },
        backdrop: "bg-black/(--opacity-dim)",
      }
    return {
      container: "min-h-(--min-h-hero-sm) max-h-(--h-hero-max-landscape) aspect-video",
      image: "object-cover",
      imageStyle: { objectPosition: "50% 40%" },
      backdrop: "bg-(--bg-surface)/(--opacity-dim)",
    }
  }, [heroRatio])

  const query = useQuery<NewsItem, Error>({
    queryKey: ["news", id, language],
    queryFn: () => fetchNews(id),
    enabled: !!id,
    staleTime: 60000,
    retry: 1,
  })

  /* ── Side-effects ── */
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  useEffect(() => {
    if (!snackbar) return
    const t = window.setTimeout(() => setSnackbar(""), TIMEOUTS.TOAST_SHORT)
    return () => window.clearTimeout(t)
  }, [snackbar])

  /* ── Handlers ── */
  const resetPreview = () => {
    if (previewUrl) { URL.revokeObjectURL(previewUrl); setPreviewUrl(null) }
    if (imageInputRef.current) imageInputRef.current.value = ""
    setNewImage(null)
  }

  const openEdit = () => {
    if (!query.data) return
    setEditData({
      title: query.data.title || "",
      content: query.data.content || "",
      title_en: query.data.title_en || "",
      content_en: query.data.content_en || "",
      image_url: query.data.image_url || "",
    })
    resetPreview()
    setEditOpen(true)
  }

  const closeEdit = () => { resetPreview(); setEditOpen(false) }

  const handleImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setNewImage(file)
    setPreviewUrl(URL.createObjectURL(file))
  }

  const handleSave = async () => {
    if (!query.data) return
    setSaving(true)
    try {
      let imageUrl = editData.image_url
      if (newImage) imageUrl = await uploadNewsImage(newImage)
      const { data } = await updateNews(query.data.id, {
        title: editData.title,
        content: editData.content,
        title_en: editData.title_en,
        content_en: editData.content_en,
        image_url: imageUrl,
      })
      queryClient.setQueryData(["news", id, language], data)
      await queryClient.invalidateQueries({ queryKey: ["news", "list"] })
      setSnackbar(t("news:notifications.savedError"))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!query.data) return
    setDeleting(true)
    try {
      await deleteNews(query.data.id)
      setSnackbar(t("news:notifications.deleted"))
      queryClient.removeQueries({ queryKey: ["news", id] })
      await queryClient.invalidateQueries({ queryKey: ["news", "list"] })
      if (window.history.length > 1) window.history.back()
      else navigate({ to: "/news" })
    } catch (_error) {
      setSnackbar(t("news:notifications.deleteError"))
    } finally {
      setDeleting(false)
      setConfirmDeleteOpen(false)
    }
  }

  const handleBack = () => {
    if (window.history.length > 1) window.history.back()
    else navigate({ to: "/news" })
  }

  /* ── Derived data ── */
  const rawImageUrl = useMemo(
    () => (editOpen ? editData.image_url : query.data?.image_url) || "",
    [editData.image_url, editOpen, query.data?.image_url]
  )
  const imageUrl = useMemo(() => previewUrl || rawImageUrl, [previewUrl, rawImageUrl])

  useEffect(() => { setHeroRatio(null) }, [imageUrl])

  const displayTitle = useMemo(() => {
    const loc = query.data?.title ?? ""
    const en = query.data?.title_en ?? ""
    return language === "en" && en.trim() ? en : loc || en
  }, [language, query.data?.title, query.data?.title_en])

  const content = useMemo(() => {
    const loc = query.data?.content ?? ""
    const en = query.data?.content_en ?? ""
    return language === "en" && en.trim() ? en : loc || en
  }, [language, query.data?.content, query.data?.content_en])

  const createdAt = query.data?.created_at
  const createdAtIso = useMemo(() => createdAt ? toDate(createdAt).toISOString() : "", [createdAt])
  const createdAtLabel = useMemo(() => createdAt ? getMoscowDate(createdAt) : "", [createdAt])

  /* ── Related articles ── */
  const category = useMemo(
    () => query.data ? inferCategory(query.data.title, query.data.content) : "general" as const,
    [query.data]
  )
  const relatedArticles = useRelatedNews(id, category, 3)

  const readingTimeMinutes = useMemo(() => {
    const text = content.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
    if (!text) return null
    const words = text.split(/\s+/).filter(Boolean).length
    return words ? Math.max(1, Math.round(words / 220)) : null
  }, [content])

  /* ══════════════════════════════════════════════════════
     LOADING STATE
     ══════════════════════════════════════════════════════ */
  if (query.isLoading) {
    return (
      <div className="news-theme aurora-mesh relative min-h-screen">
        <NewsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
        <div className="relative z-base px-4 sm:px-6 md:px-10 lg:px-14 py-8">
          <div className="max-w-4xl space-y-6">
            <Skeleton width="6rem" height="2.5rem" rounded="9999rem" />
            <Skeleton width="65%" height="2.75rem" />
            <div className="flex flex-wrap gap-3">
              <Skeleton width="10rem" height="1.75rem" rounded="9999rem" />
              <Skeleton width="7rem" height="1.75rem" rounded="9999rem" />
            </div>
            <div className="rounded-2xl overflow-hidden glass-layer-elevated glass-noise">
              <Skeleton className="w-full" height="22rem" rounded={false} />
            </div>
            <div className="glass-layer-surface glass-noise rounded-2xl p-8 space-y-4">
              <Skeleton width="100%" height="1rem" />
              <Skeleton width="96%" height="1rem" />
              <Skeleton width="90%" height="1rem" />
              <Skeleton width="80%" height="1rem" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  /* ══════════════════════════════════════════════════════
     ERROR STATE
     ══════════════════════════════════════════════════════ */
  if (query.isError || !query.data) {
    return (
      <div className="news-theme aurora-mesh relative min-h-[60vh] flex items-center justify-center px-4">
        <NewsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
        <div className="relative z-base glass-layer-surface glass-noise rounded-2xl p-8 sm:p-10 max-w-[28rem] text-center space-y-4">
          <p className="text-lg font-semibold text-(--error-text)">
            {t("news:states.loadError")}
          </p>
          <Button variant="glass" onClick={handleBack}>
            {t("common:buttons.back")}
          </Button>
        </div>
      </div>
    )
  }

  /* ══════════════════════════════════════════════════════
     MAIN RENDER
     ══════════════════════════════════════════════════════ */
  return (
    <>
        <div className="news-theme aurora-mesh relative min-h-screen overflow-clip touch-pan-y" {...swipeHandlers}>
          {/* ── Backdrop ── */}
          <NewsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

          {/* ── Content ── */}
          <div className="relative z-base px-4 sm:px-6 md:px-10 lg:px-14 pb-20 pt-6 sm:pt-8">
            <SEO title={displayTitle} description={content.slice(0, 160)} image={imageUrl} />

            {/* Back button */}
            <Button
              variant="glass"
              onClick={handleBack}
              leadingIcon={<ArrowBackIcon size={18} />}
              className="mb-6"
            >
              {t("common:buttons.back")}
            </Button>

            <article className="max-w-4xl space-y-8">
              {/* ─── HEADER ─── */}
              <header className="space-y-4">
                <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary leading-tight">
                  {displayTitle}
                </h1>

                {/* Meta pills */}
                <div className="flex flex-wrap items-center gap-2">
                  {createdAt && (
                    <span className="inline-flex items-center gap-2 rounded-full glass-layer-surface border border-glass-border/(--opacity-soft) px-3 py-1.5 text-xs font-semibold shadow-sm">
                      <Calendar size={13} className="text-brand" />
                      <time dateTime={createdAtIso} className="text-text-primary uppercase tracking-wide">
                        {createdAtLabel}
                      </time>
                    </span>
                  )}

                  {readingTimeMinutes !== null && (
                    <span className="inline-flex items-center gap-2 rounded-full glass-layer-surface border border-glass-border/(--opacity-soft) px-3 py-1.5 text-xs font-medium shadow-sm">
                      <Clock size={13} className="text-brand" />
                      <span className="text-text-primary">
                        {t("news:meta.readingTime", { count: readingTimeMinutes })}
                      </span>
                    </span>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="glass"
                    size="sm"
                    onClick={() => { void handleShare() }}
                    leadingIcon={<ShareIcon size={16} />}
                    loading={sharing}
                    aria-label={t("news:aria.shareNews") ?? ""}
                  >
                    {t("news:actions.share")}
                  </Button>

                  <Button
                    variant="glass"
                    size="sm"
                    onClick={() => toggleLike()}
                    leadingIcon={
                      <HeartIcon
                        size={16}
                        className={cn(
                          isLiked
                            ? "fill-(--error-text) text-(--error-text)"
                            : "text-(--text-secondary)"
                        )}
                      />
                    }
                    className={cn(
                      "transition-colors duration-fast",
                      isLiked && "border-(--error-text)/(--opacity-dim) bg-(--error-text)/(--opacity-subtle)"
                    )}
                  >
                    <span className="tabular-nums">{likesCount}</span>
                  </Button>

                  {/* Bookmark */}
                  <Button
                    variant="glass"
                    size="sm"
                    onClick={handleToggleBookmark}
                    leadingIcon={
                      bookmarked
                        ? <BookmarkCheckIcon size={16} className="fill-brand text-brand" />
                        : <BookmarkIcon size={16} />
                    }
                    className={cn(
                      "transition-colors duration-fast",
                      bookmarked && "border-brand/(--opacity-dim) bg-brand/(--opacity-subtle)"
                    )}
                    aria-label={bookmarked
                      ? t("news:actions.removeBookmark", { defaultValue: "Remove bookmark" })
                      : t("news:actions.bookmark", { defaultValue: "Bookmark" })
                    }
                  >
                    {bookmarked
                      ? t("news:actions.saved", { defaultValue: "Saved" })
                      : t("news:actions.bookmark", { defaultValue: "Save" })
                    }
                  </Button>

                  {/* Admin actions */}
                  {user?.role === "admin" && (
                    <>
                      <button
                        type="button"
                        onClick={openEdit}
                        className={iconBtnClass}
                        aria-label={t("news:aria.editNews") ?? ""}
                        disabled={saving || deleting}
                      >
                        <EditIcon size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteOpen(true)}
                        className={cn(iconBtnClass, "text-(--error-text) hover:text-(--error-text)")}
                        aria-label={t("news:aria.deleteNews") ?? ""}
                        disabled={deleting || saving}
                      >
                        <DeleteIcon size={16} />
                      </button>
                    </>
                  )}
                </div>
              </header>

              {/* ─── HERO IMAGE ─── */}
                <figure className="overflow-hidden rounded-2xl glass-layer-elevated glass-noise border border-glass-border/(--opacity-soft) shadow-glass">
                  <div
                    className={cn(
                      "flex w-full items-center justify-center overflow-hidden",
                      heroFrame.container,
                      heroFrame.backdrop
                    )}
                  >
                    <SmartImage
                      srcRaw={imageUrl}
                      alt={
                        displayTitle
                          ? t("news:alt.hero", { title: displayTitle })
                          : t("news:alt.heroFallback")
                      }
                      onLoad={handleHeroLoad}
                      className={cn("h-full w-full", heroFrame.image)}
                      style={heroFrame.imageStyle}
                    />
                  </div>
                  {!displayTitle && (
                    <figcaption className="border-t border-glass-border/(--opacity-soft) bg-(--bg-surface)/(--opacity-subtle) px-5 py-3 text-sm font-medium text-(--text-secondary)">
                      {t("news:alt.heroFallback")}
                    </figcaption>
                  )}
                </figure>

              {/* ─── ARTICLE BODY ─── */}
                <section className="glass-layer-surface glass-noise rounded-2xl p-6 sm:p-8 md:p-10">
                  <div className="news-article-body text-body leading-relaxed text-(--text-secondary)">
                    {content?.split(/\n{2,}/).map((chunk: string, idx: number) => {
                      const text = chunk.trim()
                      if (!text) return null

                      // Pull-quote: lines starting with >
                      if (text.startsWith(">")) {
                        return (
                          <blockquote key={`q-${idx}`} className="news-pullquote">
                            {text.replace(/^>\s*/, "")}
                          </blockquote>
                        )
                      }

                      // Drop cap on first paragraph (only if long enough)
                      const isDropCap = idx === 0 && text.length > 200
                      return (
                        <p key={`p-${idx}`} className={isDropCap ? "news-dropcap" : undefined}>
                          {text}
                        </p>
                      )
                    })}
                  </div>
                </section>

              {/* ─── COMMENTS ─── */}
                <NewsComments
                  comments={comments}
                  user={user as { id: string; role: string } | null}
                  isCommenting={isCommenting}
                  addComment={addComment}
                  updateComment={updateComment}
                  deleteComment={deleteComment}
                  t={t}
                  getMoscowDate={getMoscowDate}
                />

              {/* ─── RELATED ARTICLES ─── */}
              {relatedArticles.length > 0 && (
                <RelatedNews items={relatedArticles} />
              )}

              {/* ─── PREV / NEXT NAVIGATION ─── */}
              {(prevId || nextId) && (
                  <nav
                    className="flex items-stretch gap-4 border-t border-glass-border/(--opacity-soft) pt-6"
                    aria-label={t("news:navigation.label", { defaultValue: "Article navigation" })}
                  >
                    {prevId ? (
                      <Link
                        to="/news/$id"
                        params={{ id: prevId }}
                        className="group flex flex-1 flex-col gap-1 rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) p-4 transition hover:shadow-glass hover:-translate-y-0.5"
                      >
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
                          {t("news:navigation.prev", { defaultValue: "Previous" })}
                        </span>
                        <span className="text-sm font-semibold text-text-primary line-clamp-1 group-hover:text-brand transition-colors">
                          {prevTitle}
                        </span>
                      </Link>
                    ) : (
                      <div className="flex-1" />
                    )}

                    {nextId ? (
                      <Link
                        to="/news/$id"
                        params={{ id: nextId }}
                        className="group flex flex-1 flex-col gap-1 rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) p-4 text-right transition hover:shadow-glass hover:-translate-y-0.5"
                      >
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
                          {t("news:navigation.next", { defaultValue: "Next" })}
                        </span>
                        <span className="text-sm font-semibold text-text-primary line-clamp-1 group-hover:text-brand transition-colors">
                          {nextTitle}
                        </span>
                      </Link>
                    ) : (
                      <div className="flex-1" />
                    )}
                  </nav>
              )}
            </article>
          </div>
        </div>

      {/* ═══ SHARE DIALOG ═══ */}
      <Dialog
        open={shareDialogOpen}
        onClose={() => setShareDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{t("news:shareDialog.title")}</DialogTitle>
        <DialogContent className="space-y-6 pt-4">
          <p className="text-base leading-relaxed text-(--text-secondary)">
            {t("news:shareDialog.description")}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            {shareOptions.map((option) => {
              const Icon = option.icon
              return (
                <a
                  key={`share-${option.id}`}
                  href={option.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setShareDialogOpen(false)}
                  className="group flex items-center gap-3 rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) px-4 py-3 transition hover:border-glass-border hover:shadow-sm"
                >
                  <span
                    className={cn(
                      "inline-flex h-10 w-10 items-center justify-center rounded-full bg-(--bg-surface)/(--opacity-hover) shadow-sm transition group-hover:scale-105",
                      option.accent
                    )}
                  >
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="text-sm font-semibold text-text-primary">
                    {option.label}
                  </span>
                </a>
              )
            })}
          </div>
        </DialogContent>
        <DialogActions className="p-6">
          <Button
            variant="solid"
            onClick={() => { void handleCopyLink() }}
            disabled={copyingLink}
            className="w-full sm:w-auto"
          >
            <div className="flex items-center gap-2">
              <CopyIcon className="h-4 w-4" />
              {copiedLink
                ? t("news:shareDialog.copySuccess")
                : t("news:shareDialog.copy")}
            </div>
          </Button>
        </DialogActions>
      </Dialog>

      {/* ═══ EDIT DIALOG ═══ */}
      <Dialog open={editOpen} onClose={closeEdit} maxWidth="lg" fullWidth>
        <DialogTitle>{t("news:dialogs.edit.title")}</DialogTitle>
        <DialogContent className="space-y-6 pt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <Field label={t("news:form.title") ?? ""} htmlFor="edit-title" required>
                <Input
                  id="edit-title"
                  ref={editTitleRef}
                  type="text"
                  value={editData.title}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setEditData({ ...editData, title: e.target.value })
                  }
                  maxLength={100}
                />
              </Field>
              <Field label={t("news:form.content") ?? ""} htmlFor="edit-content" required>
                <Textarea
                  id="edit-content"
                  value={editData.content}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                    setEditData({ ...editData, content: e.target.value })
                  }
                  maxLength={3000}
                  rows={6}
                />
              </Field>
            </div>
            <div className="space-y-4">
              <Field
                label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
                htmlFor="edit-title-en"
              >
                <Input
                  id="edit-title-en"
                  type="text"
                  value={editData.title_en}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setEditData({ ...editData, title_en: e.target.value })
                  }
                  maxLength={100}
                />
              </Field>
              <Field
                label={t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""}
                htmlFor="edit-content-en"
              >
                <Textarea
                  id="edit-content-en"
                  value={editData.content_en}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                    setEditData({ ...editData, content_en: e.target.value })
                  }
                  maxLength={3000}
                  rows={6}
                />
              </Field>
              <div className="space-y-3">
                <label className="block text-sm font-semibold text-(--text-secondary)">
                  {t("news:form.image", { defaultValue: "Cover Image" })}
                </label>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <Button
                    as="label"
                    variant="glass"
                    className="w-full sm:w-auto"
                    disabled={saving}
                  >
                    <div className="flex items-center gap-2">
                      <PhotoCamera className="h-4 w-4" />
                      {newImage
                        ? t("common:buttons.changePhoto")
                        : t("common:buttons.uploadPhoto")}
                    </div>
                    <input
                      type="file"
                      accept="image/*"
                      hidden
                      ref={imageInputRef}
                      onChange={handleImageChange}
                    />
                  </Button>
                  {imageUrl && (
                    <div className="overflow-hidden rounded-lg border border-glass-border/(--opacity-soft) shadow-sm">
                      <SmartImage
                        srcRaw={imageUrl}
                        alt={t("news:alt.editPreview")}
                        className="h-14 w-28 object-cover"
                      />
                    </div>
                  )}
                </div>
                {previewUrl && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={resetPreview}
                    className="text-(--error-text)"
                  >
                    {t("common:buttons.reset")}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
        <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
          <Button variant="ghost" onClick={closeEdit} className="w-full sm:w-auto">
            {t("common:buttons.cancel")}
          </Button>
          <Button
            variant="solid"
            onClick={handleSave}
            disabled={!editData.title.trim() || !editData.content.trim() || saving}
            className="w-full sm:w-auto min-w-32"
          >
            {saving ? t("common:buttons.saving") : t("common:buttons.save")}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ═══ CONFIRM DELETE ═══ */}
      <ConfirmDialog
        open={confirmDeleteOpen}
        title={t("news:dialogs.delete.title")}
        message={t("news:dialogs.delete.description")}
        confirmText={t("common:buttons.delete")}
        cancelText={t("common:buttons.cancel")}
        variant="danger"
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmDeleteOpen(false)}
        isLoading={deleting}
      />

      {/* ═══ SNACKBAR ═══ */}
      {snackbar && (
        <Snackbar
          open={!!snackbar}
          autoHideDuration={2400}
          onClose={() => setSnackbar("")}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
          className="z-navbar"
        >
          <Alert severity="success" onClose={() => setSnackbar("")}>
            {snackbar}
          </Alert>
        </Snackbar>
      )}
    </>
  )
}
