import { ContentCard, Snackbar, ConfirmDialog } from "@/components/ui"
<<<<<<< HEAD
import { SpotlightOverlay, useSpotlight } from "@/components/ui/Spotlight"
import { motion as motionTokens } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { sanitizeNewsText } from "@/utils/sanitize"
import { motion } from "framer-motion"
import { FC, lazy, Suspense, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import NewsCardContent from "./NewsCardContent"
import NewsCardHero from "./NewsCardHero"
import type { NewsEditData } from "./NewsCardEditDialog"
=======
import { SpotlightOverlay } from "@/components/ui/Spotlight"
import { motion as motionTokens } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { motion, MotionValue } from "framer-motion"
import { FC, Suspense, lazy } from "react"
import NewsCardContent from "./NewsCardContent"
import NewsCardHero from "./NewsCardHero"
>>>>>>> origin/main

const NewsCardActions = lazy(() =>
  import("./NewsCardActions").then((m) => ({ default: m.NewsCardActions }))
)
const NewsCardEditDialog = lazy(() =>
  import("./NewsCardEditDialog").then((m) => ({ default: m.NewsCardEditDialog }))
)

<<<<<<< HEAD
export type NewsCardViewProps = {
  id: string
  title: string
  contentRaw: string
  created_at: string
  image_url?: string
  isLiked: boolean
  likesCount: number
  commentsCount: number
  onToggleLike: () => void
  isAdmin: boolean

  // Edit State
  editOpen: boolean
  onOpenEdit: () => void
  onCloseEdit: () => void
  editData: NewsEditData
  onEditSuccess?: () => void

  // Delete State
  confirmDeleteOpen: boolean
  onOpenDelete: () => void
  onCloseDelete: () => void
  onConfirmDelete: () => void

  // Status
  loading: boolean
  error: string
  onErrorClose: () => void
=======
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
>>>>>>> origin/main
}

export const NewsCardView: FC<NewsCardViewProps> = ({
  id,
  title,
<<<<<<< HEAD
  contentRaw,
  created_at,
  image_url,
  isLiked,
  likesCount,
  commentsCount,
  onToggleLike,
  isAdmin,
  editOpen,
  onOpenEdit,
  onCloseEdit,
  editData,
  onEditSuccess,
  confirmDeleteOpen,
  onOpenDelete,
  onCloseDelete,
  onConfirmDelete,
  loading,
  error,
  onErrorClose,
}) => {
  const { t } = useTranslation(["news", "common"])
  const spotlight = useSpotlight()

  const [sanitizedPreview, setSanitizedPreview] = useState("")

  useEffect(() => {
    let mounted = true
    void sanitizeNewsText(contentRaw).then((text) => {
      if (mounted) setSanitizedPreview(text)
    })
    return () => {
      mounted = false
    }
  }, [contentRaw])

  const hoveringDisabled = editOpen

=======
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
  t
}) => {
>>>>>>> origin/main
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      onMouseMove={spotlight.onMouseMove}
      transition={{ duration: motionTokens.durationMedium, ease: [0.22, 1, 0.36, 1] }}
      whileHover={!hoveringDisabled ? { y: -4 } : undefined}
<<<<<<< HEAD
      className={cn("h-full outline-none", "cursor-default")}
=======
      className={cn("h-full outline-none", hoveringDisabled ? "cursor-default" : "cursor-pointer")}
>>>>>>> origin/main
    >
      <ContentCard
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
<<<<<<< HEAD
                onEdit={onOpenEdit}
                onDelete={onOpenDelete}
=======
                onEdit={onEditOpen}
                onDelete={onDeleteOpen}
>>>>>>> origin/main
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
<<<<<<< HEAD
            preview={sanitizedPreview}
=======
            preview={previewText}
>>>>>>> origin/main
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
<<<<<<< HEAD
            onClose={onCloseEdit}
=======
            onClose={onEditClose}
>>>>>>> origin/main
            initialData={editData}
            onSuccess={onEditSuccess}
          />
        </Suspense>

        <ConfirmDialog
          open={confirmDeleteOpen}
<<<<<<< HEAD
          title={t("news:dialogs.delete.title")}
          message={t("news:dialogs.delete.description")}
          confirmText={t("common:buttons.delete")}
          cancelText={t("common:buttons.cancel")}
          variant="danger"
          onConfirm={() => void onConfirmDelete()}
          onCancel={onCloseDelete}
=======
          title={t.deleteTitle}
          message={t.deleteDesc}
          confirmText={t.confirm}
          cancelText={t.cancel}
          variant="danger"
          onConfirm={onDeleteConfirm}
          onCancel={onDeleteClose}
>>>>>>> origin/main
          isLoading={loading}
        />
        <Snackbar open={!!error} message={error} onClose={onErrorClose} />
      </ContentCard>
    </motion.article>
  )
}
