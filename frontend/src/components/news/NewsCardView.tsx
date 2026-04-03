import { Snackbar, ConfirmDialog } from "@/components/ui"
import { SpotlightOverlay } from "@/components/ui/Spotlight"
import { motion as motionTokens } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { motion, MotionValue } from "framer-motion"
import { FC, Suspense, lazy, useState, useCallback } from "react"
import NewsCardContent from "./NewsCardContent"
import NewsCardHero from "./NewsCardHero"
import { NewsQuickView } from "./NewsQuickView"
import { NewsCategoryBadge } from "./NewsCategoryBadge"
import type { NewsCategory } from "@/features/news/categories"
import { clearNewsHeroId } from "@/utils/newsTransition"

const NewsCardActions = lazy(() =>
  import("./NewsCardActions").then((m) => ({ default: m.NewsCardActions }))
)
const NewsCardEditDialog = lazy(() =>
  import("./NewsCardEditDialog").then((m) => ({ default: m.NewsCardEditDialog }))
)

export interface NewsCardViewProps {
  id: string
  title: string
  created_at: string
  image_url?: string
  previewText: string
  isLiked: boolean
  likesCount: number
  commentsCount: number
  isBookmarked: boolean
  isAdmin: boolean
  loading: boolean
  error: string
  hoveringDisabled: boolean
  category: NewsCategory
  editOpen: boolean
  confirmDeleteOpen: boolean
  editData: {
    title: string
    content: string
    title_en: string
    content_en: string
    image_url: string
  }
  spotlight: {
    mouseX: MotionValue<number>
    mouseY: MotionValue<number>
    onMouseMove: (e: React.MouseEvent<HTMLDivElement>) => void
  }
  onToggleLike: () => void
  onToggleBookmark: () => void
  onEditOpen: () => void
  onEditClose: () => void
  onDeleteOpen: () => void
  onDeleteClose: () => void
  onDeleteConfirm: () => void
  onEditSuccess: () => void
  onErrorClose: () => void
  t: {
    deleteTitle: string
    deleteDesc: string
    confirm: string
    cancel: string
  }
}

export const NewsCardView: FC<NewsCardViewProps> = ({
  id,
  title,
  created_at,
  image_url,
  previewText,
  isLiked,
  likesCount,
  commentsCount,
  isBookmarked,
  isAdmin,
  loading,
  error,
  hoveringDisabled,
  category,
  editOpen,
  confirmDeleteOpen,
  editData,
  spotlight,
  onToggleLike,
  onToggleBookmark,
  onEditOpen,
  onEditClose,
  onDeleteOpen,
  onDeleteClose,
  onDeleteConfirm,
  onEditSuccess,
  onErrorClose,
  t,
}) => {
  /* ── Quick-view hover state ── */
  const [quickViewVisible, setQuickViewVisible] = useState(false)
  const showQuickView = useCallback(() => {
    if (!hoveringDisabled) setQuickViewVisible(true)
  }, [hoveringDisabled])
  const hideQuickView = useCallback(() => setQuickViewVisible(false), [])

  /* ── View Transition: mark hero for morphing on navigation ── */
  const [transitioning, setTransitioning] = useState(false)
  const handlePointerDown = useCallback(() => {
    if (!hoveringDisabled) {
      clearNewsHeroId() // Prevent duplicate VT name with stale back-nav ID
      setTransitioning(true)
    }
  }, [hoveringDisabled])
  // Reset if user cancels (e.g., right-click, drag, pointerleave without click)
  const handleTransitionReset = useCallback(() => setTransitioning(false), [])

  return (
    <motion.article
      onMouseMove={spotlight.onMouseMove}
      onMouseEnter={showQuickView}
      onMouseLeave={() => { hideQuickView(); handleTransitionReset() }}
      onPointerDown={handlePointerDown}
      whileHover={!hoveringDisabled ? { y: -4 } : undefined}
      transition={{ duration: motionTokens.durationMedium, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "news-card-container relative h-full rounded-2xl overflow-hidden card-matte glass-noise dash-border-shimmer group outline-none transition-shadow duration-base",
        hoveringDisabled
          ? "cursor-default"
          : "cursor-pointer hover:shadow-premium-lift"
      )}
      data-testid="news-card"
    >
      {/* Quick-view popover */}
      <NewsQuickView
          visible={quickViewVisible}
          title={title}
          preview={previewText}
          created_at={created_at}
          likesCount={likesCount}
          commentsCount={commentsCount}
          category={category}
        />

      {/* Spotlight */}
      <SpotlightOverlay
        mouseX={spotlight.mouseX}
        mouseY={spotlight.mouseY}
        className="z-hide"
      />

      {/* Admin menu */}
      {isAdmin && (
        <div className="absolute right-3 top-3 z-surface">
          <Suspense fallback={null}>
            <NewsCardActions
              id={id}
              onEdit={onEditOpen}
              onDelete={onDeleteOpen}
              isDisabled={loading}
            />
          </Suspense>
        </div>
      )}

      {/* Category badge — top-left */}
      <div className="absolute left-3 top-3 z-surface">
        <NewsCategoryBadge category={category} size="sm" />
      </div>

      {/* Image */}
      <div className="relative shrink-0 overflow-hidden h-48 sm:h-52">
        <NewsCardHero
          id={id}
          image_url={image_url}
          title={title}
          created_at={created_at}
          transitioning={transitioning}
        />
      </div>

      {/* Content — no `relative` here: Link's before:absolute before:inset-0
           must reach <article> to make the entire card clickable (FIX-57-02) */}
      <div className="flex flex-1 flex-col">
        <NewsCardContent
          id={id}
          title={title}
          preview={previewText}
          isLiked={isLiked}
          likesCount={likesCount}
          commentsCount={commentsCount}
          isBookmarked={isBookmarked}
          onToggleLike={onToggleLike}
          onToggleBookmark={onToggleBookmark}
          hoveringDisabled={hoveringDisabled}
        />
      </div>

      {/* Dialogs */}
      <Suspense fallback={null}>
        <NewsCardEditDialog
          id={id}
          open={editOpen}
          onClose={onEditClose}
          initialData={editData}
          onSuccess={onEditSuccess}
        />
      </Suspense>

      <ConfirmDialog
        open={confirmDeleteOpen}
        title={t.deleteTitle}
        message={t.deleteDesc}
        confirmText={t.confirm}
        cancelText={t.cancel}
        variant="danger"
        onConfirm={onDeleteConfirm}
        onCancel={onDeleteClose}
        isLoading={loading}
      />

      <Snackbar open={!!error} message={error} onClose={onErrorClose} />
    </motion.article>
  )
}
