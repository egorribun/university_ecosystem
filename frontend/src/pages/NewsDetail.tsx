import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "@tanstack/react-router"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft as ArrowBackIcon, Copy as CopyIcon } from "lucide-react"
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
import { toDate, getMoscowDate } from "@/utils/date"
import { localizeField } from "@/utils/localize"
import { deleteNews, type NewsItem } from "@/api/news"
import { newsDetailQueryOptions } from "@/api/hooks/news"
import { SEO } from "@/components/ui/SEO"
import { Button, ConfirmDialog } from "@/components/ui"
import { NewsComments } from "@/components/news/NewsComments"
import { RelatedNews } from "@/components/news/RelatedNews"
import { NewsBackdrop } from "@/components/news/NewsBackdrop"
import { NewsDetailSkeleton } from "@/components/news/NewsDetailSkeleton"
import { NewsDetailHeader } from "@/components/news/NewsDetailHeader"
import { NewsDetailHero } from "@/components/news/NewsDetailHero"
import { NewsDetailBody } from "@/components/news/NewsDetailBody"
import { NewsDetailEditDialog } from "@/components/news/NewsDetailEditDialog"
import { NewsDetailNavigation } from "@/components/news/NewsDetailNavigation"
import { useBookmarks } from "@/hooks/useBookmarks"
import { useRelatedNews } from "@/hooks/useRelatedNews"
import { useArticleNavigation } from "@/hooks/useArticleNavigation"
import { captureActiveTelemetryContext } from "@/utils/telemetryContext"
import { useSwipe } from "@/hooks/useSwipe"
import { inferCategory } from "@/features/news/categories"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { estimateReadingTime } from "@/utils/readingTime"
import { TIMEOUTS } from "@/config/timeouts"
import useMediaQuery from "@/hooks/useMediaQuery"
import { setNewsHeroId } from "@/utils/newsTransition"

/* ══════════════════════════════════════════════════════════
   NEWS DETAIL PAGE — Orchestrator
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
      if (articleId) {
        window.scrollTo({ top: 0, behavior: "instant" })
        void navigate({ to: "/news/$id", params: { id: articleId } })
      }
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
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [snackbar, setSnackbar] = useState("")

  /* ── Query ── */
  // Wave 129 SW5 — uses the shared `newsDetailQueryOptions` factory so the
  // SSR loader at `/news/$id` and this client component pull from the same
  // queryKey identity (per-request QueryClient via SsrRoot W128 SW3).
  const query = useQuery<NewsItem, Error>({
    ...newsDetailQueryOptions(id, language),
    enabled: !!id,
  })

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
    title: query.data?.title || "",
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
      initialData: query.data
        ? {
            likes_count: query.data.likes_count,
            comments_count: query.data.comments_count,
            is_liked: query.data.is_liked,
          }
        : undefined,
    })
  const isLiked = interactions?.is_liked ?? false
  const likesCount = interactions?.likes_count ?? 0
  const comments = interactions?.comments ?? []

  /* ── Store hero ID for back-navigation view transition ── */
  useEffect(() => {
    setNewsHeroId(id)
  }, [id])

  /* ── Side-effects ── */
  useEffect(() => {
    if (!snackbar) return
    const timer = window.setTimeout(() => setSnackbar(""), TIMEOUTS.TOAST_SHORT)
    return () => window.clearTimeout(timer)
  }, [snackbar])

  /* ── Firefox fallback: JS-driven reading progress bar ── */
  const progressRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let ticking = false
    let pendingFrame: number | null = null
    const onScroll = () => {
      if (ticking) return
      ticking = true
      pendingFrame = requestAnimationFrame(() => {
        pendingFrame = null
        if (progressRef.current) {
          const max = document.documentElement.scrollHeight - window.innerHeight
          const pct = max > 0 ? Math.min(window.scrollY / max, 1) : 0
          progressRef.current.style.transform = `scaleX(${pct})`
        }
        ticking = false
      })
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => {
      window.removeEventListener("scroll", onScroll)
      if (pendingFrame !== null) cancelAnimationFrame(pendingFrame)
    }
  }, [])

  /* ── Handlers ── */
  const handleDelete = async () => {
    if (!query.data) return
    const telemetryContext = captureActiveTelemetryContext()
    setDeleting(true)
    try {
      await telemetryContext.run(() => deleteNews(query.data.id))
      setSnackbar(t("news:notifications.deleted"))
      queryClient.removeQueries({ queryKey: ["news", id] })
      await telemetryContext.run(() =>
        queryClient.invalidateQueries({ queryKey: ["news", "list"] })
      )
      if (window.history.length > 1) window.history.back()
      else void navigate({ to: "/news" })
    } catch {
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
  const imageUrl = query.data?.image_url || ""

  const displayTitle = useMemo(
    () => localizeField(query.data?.title ?? "", query.data?.title_en, language),
    [language, query.data?.title, query.data?.title_en]
  )

  const content = useMemo(
    () => localizeField(query.data?.content ?? "", query.data?.content_en, language),
    [language, query.data?.content, query.data?.content_en]
  )

  const createdAt = query.data?.created_at
  const createdAtIso = useMemo(
    () => (createdAt ? toDate(createdAt).toISOString() : ""),
    [createdAt]
  )
  const createdAtLabel = useMemo(() => (createdAt ? getMoscowDate(createdAt) : ""), [createdAt])

  const category = useMemo(
    () => (query.data ? inferCategory(query.data.title, query.data.content) : ("general" as const)),
    [query.data]
  )
  const relatedArticles = useRelatedNews(id, category, 3)

  const readingTimeMinutes = useMemo(() => estimateReadingTime(content), [content])

  const editInitialData = useMemo(
    () => ({
      title: query.data?.title || "",
      content: query.data?.content || "",
      title_en: query.data?.title_en || "",
      content_en: query.data?.content_en || "",
      image_url: query.data?.image_url || "",
    }),
    [query.data]
  )

  /* ══════════════ LOADING ══════════════ */
  if (query.isLoading) {
    return <NewsDetailSkeleton isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
  }

  /* ══════════════ ERROR ══════════════ */
  if (query.isError || !query.data) {
    return (
      <div className="news-theme aurora-mesh relative min-h-[60vh] flex items-center justify-center px-4">
        <NewsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
        <div className="relative z-[1] glass-layer-surface glass-noise rounded-2xl p-8 sm:p-10 max-w-[28rem] text-center space-y-4">
          <p className="text-lg font-semibold text-(--error-text)">{t("news:states.loadError")}</p>
          <Button variant="glass" onClick={handleBack}>
            {t("common:buttons.back")}
          </Button>
        </div>
      </div>
    )
  }

  /* ══════════════ MAIN RENDER ══════════════ */
  return (
    <>
      {/* Reading progress — CSS scroll-driven animation (JS fallback for Firefox via W59-19) */}
      <div ref={progressRef} className="news-reading-progress" aria-hidden="true" />

      <div
        className="news-theme aurora-mesh relative min-h-screen overflow-clip touch-pan-y"
        {...swipeHandlers}
      >
        <NewsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

        <div className="relative z-[1] px-4 sm:px-6 md:px-10 lg:px-14 pb-20 pt-6 sm:pt-8">
          <SEO
            title={displayTitle}
            description={content
              .replace(/[#*_`[\]!|>-]/g, "")
              .replace(/\s+/g, " ")
              .trim()
              .slice(0, 160)}
            image={imageUrl}
          />

          <Button
            variant="glass"
            onClick={handleBack}
            leadingIcon={<ArrowBackIcon size={18} />}
            className="mb-6"
          >
            {t("common:buttons.back")}
          </Button>

          <article className="max-w-4xl 2xl:max-w-5xl space-y-8">
            <NewsDetailHeader
              displayTitle={displayTitle}
              createdAt={createdAt}
              createdAtIso={createdAtIso}
              createdAtLabel={createdAtLabel}
              readingTimeMinutes={readingTimeMinutes}
              isLiked={isLiked}
              likesCount={likesCount}
              bookmarked={bookmarked}
              isAdmin={user?.role === "admin"}
              saving={false}
              deleting={deleting}
              sharing={sharing}
              onShare={() => {
                void handleShare()
              }}
              onToggleLike={() => toggleLike()}
              onToggleBookmark={handleToggleBookmark}
              onEditOpen={() => setEditOpen(true)}
              onDeleteOpen={() => setConfirmDeleteOpen(true)}
            />

            <NewsDetailHero imageUrl={imageUrl} displayTitle={displayTitle} />
            <NewsDetailBody content={content} />

            <NewsComments
              comments={comments}
              user={user}
              isCommenting={isCommenting}
              addComment={addComment}
              updateComment={updateComment}
              deleteComment={deleteComment}
              t={t}
              getMoscowDate={getMoscowDate}
            />

            {relatedArticles.length > 0 && <RelatedNews items={relatedArticles} />}

            <NewsDetailNavigation
              prevId={prevId}
              nextId={nextId}
              prevTitle={prevTitle}
              nextTitle={nextTitle}
            />
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
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-3">
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
                  <span className="text-sm font-semibold text-text-primary">{option.label}</span>
                </a>
              )
            })}
          </div>
        </DialogContent>
        <DialogActions className="p-6">
          <Button
            variant="solid"
            onClick={() => {
              void handleCopyLink()
            }}
            disabled={copyingLink}
            className="w-full sm:w-auto"
          >
            <div className="flex items-center gap-2">
              <CopyIcon className="h-4 w-4" />
              {copiedLink ? t("news:shareDialog.copySuccess") : t("news:shareDialog.copy")}
            </div>
          </Button>
        </DialogActions>
      </Dialog>

      {/* ═══ EDIT DIALOG ═══ */}
      <NewsDetailEditDialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        newsId={id}
        language={language}
        initialData={editInitialData}
        onSuccess={(msg) => setSnackbar(msg)}
        onError={(msg) => setSnackbar(msg)}
      />

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
