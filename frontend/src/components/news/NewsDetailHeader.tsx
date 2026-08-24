import {
  Bookmark as BookmarkIcon,
  BookmarkCheck as BookmarkCheckIcon,
  Edit2 as EditIcon,
  Trash2 as DeleteIcon,
  Share2 as ShareIcon,
  Heart as HeartIcon,
  Clock,
  Calendar,
} from "lucide-react"
import { Button } from "@/components/ui"
import { cn } from "@/utils/cn"
import { useTranslation } from "react-i18next"

const iconBtnClass =
  "inline-flex h-10 w-10 items-center justify-center rounded-xl matte-chip text-(--text-secondary) transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/(--opacity-medium)"

interface NewsDetailHeaderProps {
  displayTitle: string
  createdAt: string | undefined
  createdAtIso: string
  createdAtLabel: string
  readingTimeMinutes: number | null
  isLiked: boolean
  likesCount: number
  bookmarked: boolean
  isAdmin: boolean
  saving: boolean
  deleting: boolean
  sharing: boolean
  onShare: () => void
  onToggleLike: () => void
  onToggleBookmark: () => void
  onEditOpen: () => void
  onDeleteOpen: () => void
}

export function NewsDetailHeader({
  displayTitle,
  createdAt,
  createdAtIso,
  createdAtLabel,
  readingTimeMinutes,
  isLiked,
  likesCount,
  bookmarked,
  isAdmin,
  saving,
  deleting,
  sharing,
  onShare,
  onToggleLike,
  onToggleBookmark,
  onEditOpen,
  onDeleteOpen,
}: NewsDetailHeaderProps) {
  const { t } = useTranslation(["news", "common"])

  return (
    <header className="space-y-4">
      <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary leading-tight">
        {displayTitle}
      </h1>

      {/* Meta pills */}
      <div className="flex flex-wrap items-center gap-2">
        {createdAt && (
          <span className="inline-flex items-center gap-2 rounded-full matte-chip px-3 py-1.5 text-xs font-semibold">
            <Calendar size={13} className="text-brand" aria-hidden="true" />
            <time dateTime={createdAtIso} className="text-text-primary uppercase tracking-wide">
              {createdAtLabel}
            </time>
          </span>
        )}

        {readingTimeMinutes !== null && (
          <span className="inline-flex items-center gap-2 rounded-full matte-chip px-3 py-1.5 text-xs font-medium">
            <Clock size={13} className="text-brand" aria-hidden="true" />
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
          onClick={onShare}
          leadingIcon={<ShareIcon size={16} />}
          loading={sharing}
          aria-label={t("news:aria.shareNews")}
        >
          {t("news:actions.share")}
        </Button>

        <Button
          variant="glass"
          size="sm"
          onClick={onToggleLike}
          leadingIcon={
            <HeartIcon
              size={16}
              className={cn(
                isLiked ? "fill-(--error-text) text-(--error-text)" : "text-(--text-secondary)"
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
          onClick={onToggleBookmark}
          leadingIcon={
            bookmarked ? (
              <BookmarkCheckIcon size={16} className="fill-brand text-brand" />
            ) : (
              <BookmarkIcon size={16} />
            )
          }
          className={cn(
            "transition-colors duration-fast",
            bookmarked && "border-brand/(--opacity-dim) bg-brand/(--opacity-subtle)"
          )}
          aria-label={
            bookmarked
              ? t("news:actions.removeBookmark")
              : t("news:actions.bookmark", { defaultValue: "Bookmark" })
          }
        >
          {bookmarked ? t("news:actions.saved") : t("news:actions.bookmark")}
        </Button>

        {/* Admin actions — separated by border */}
        {isAdmin && (
          <>
            <span
              className="h-6 w-px bg-glass-border/(--opacity-soft) mx-1 hidden sm:block"
              aria-hidden="true"
            />
            <button
              type="button"
              onClick={onEditOpen}
              className={iconBtnClass}
              aria-label={t("news:aria.editNews")}
              disabled={saving || deleting}
            >
              <EditIcon size={16} />
            </button>
            <button
              type="button"
              onClick={onDeleteOpen}
              className={cn(iconBtnClass, "text-(--error-text) hover:text-(--error-text)")}
              aria-label={t("news:aria.deleteNews")}
              disabled={deleting || saving}
            >
              <DeleteIcon size={16} />
            </button>
          </>
        )}
      </div>
    </header>
  )
}
