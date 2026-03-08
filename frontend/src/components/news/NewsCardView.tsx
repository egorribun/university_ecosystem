import { ContentCard, Snackbar, ConfirmDialog } from "@/components/ui"
import { SpotlightOverlay } from "@/components/ui/Spotlight"
import { motion as motionTokens } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { motion, MotionValue } from "framer-motion"
import { FC, Suspense, lazy } from "react"
import NewsCardContent from "./NewsCardContent"
import NewsCardHero from "./NewsCardHero"

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

  // Interaction State
  isLiked: boolean
  likesCount: number
  commentsCount: number

  // Container State
  isAdmin: boolean
  loading: boolean
  error: string
  hoveringDisabled: boolean

  // Dialog State
  editOpen: boolean
  confirmDeleteOpen: boolean
  editData: {
    title: string
    content: string
    title_en: string
    content_en: string
    image_url: string
  }

  // Spotlight
  spotlight: {
    mouseX: MotionValue<number>
    mouseY: MotionValue<number>
    onMouseMove: (e: React.MouseEvent<HTMLDivElement>) => void
  }

  // Handlers
  onToggleLike: () => void
  onEditOpen: () => void
  onEditClose: () => void
  onDeleteOpen: () => void
  onDeleteClose: () => void
  onDeleteConfirm: () => void
  onEditSuccess: () => void
  onErrorClose: () => void

  // Translations
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
  isAdmin,
  loading,
  error,
  hoveringDisabled,
  editOpen,
  confirmDeleteOpen,
  editData,
  spotlight,
  onToggleLike,
  onEditOpen,
  onEditClose,
  onDeleteOpen,
  onDeleteClose,
  onDeleteConfirm,
  onEditSuccess,
  onErrorClose,
  t,
}) => {
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      onMouseMove={spotlight.onMouseMove}
      transition={{ duration: motionTokens.durationMedium, ease: [0.22, 1, 0.36, 1] }}
      whileHover={!hoveringDisabled ? { y: -4 } : undefined}
      className={cn("h-full outline-none", hoveringDisabled ? "cursor-default" : "cursor-pointer")}
    >
      <ContentCard
        data-testid="news-card"
        hoverable={!hoveringDisabled}
        className={cn(
          "card-news group h-full",
          hoveringDisabled ? "cursor-default" : "card-interactive"
        )}
      >
        <SpotlightOverlay mouseX={spotlight.mouseX} mouseY={spotlight.mouseY} className="z-hide" />

        {isAdmin && (
          <ContentCard.Actions className="absolute right-2 top-2 z-surface">
            <Suspense fallback={null}>
              <NewsCardActions
                id={id}
                onEdit={onEditOpen}
                onDelete={onDeleteOpen}
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
          <NewsCardHero image_url={image_url} title={title} created_at={created_at} />

          <NewsCardContent
            id={id}
            title={title}
            preview={previewText}
            isLiked={isLiked}
            likesCount={likesCount}
            commentsCount={commentsCount}
            onToggleLike={onToggleLike}
            hoveringDisabled={hoveringDisabled}
          />
        </div>

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
      </ContentCard>
    </motion.article>
  )
}
