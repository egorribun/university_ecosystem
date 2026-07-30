import { cn } from "@/utils/cn"
import {
  ArrowUpRight as ArrowIcon,
  Bookmark as BookmarkIcon,
  BookmarkCheck as BookmarkCheckIcon,
  Clock as ClockIcon,
  MessageCircle as CommentIcon,
  Heart as HeartIcon,
} from "lucide-react"
import { memo, useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "@tanstack/react-router"

interface NewsCardContentProps {
  id: string
  title: string
  preview: string
  isLiked: boolean
  likesCount: number
  commentsCount: number
  isBookmarked?: boolean
  readingTime?: number | null
  onToggleLike: () => void
  onToggleBookmark?: () => void
  hoveringDisabled: boolean
}

const NewsCardContent = ({
  id,
  title,
  preview,
  isLiked,
  likesCount,
  commentsCount,
  isBookmarked = false,
  readingTime,
  onToggleLike,
  onToggleBookmark,
  hoveringDisabled,
}: NewsCardContentProps) => {
  const { t } = useTranslation(["common"])
  const [celebrating, setCelebrating] = useState(false)

  const handleLike = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!isLiked) {
        setCelebrating(true)
        setTimeout(() => setCelebrating(false), 400)
      }
      onToggleLike()
    },
    [isLiked, onToggleLike]
  )

  return (
    <div className="flex flex-1 flex-col gap-3 p-5">
      {/* Title — Wave 116 SW3: h2 keeps heading-order sequential under page h1 */}
      <h2 className="font-semibold leading-snug text-text-primary text-base line-clamp-2">
        <Link
          to="/news/$id"
          params={{ id }}
          className={cn(
            "before:absolute before:inset-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/(--opacity-medium) focus-visible:ring-offset-2",
            hoveringDisabled && "pointer-events-none"
          )}
        >
          {title}
        </Link>
      </h2>

      {/* Preview */}
      <p className="text-sm leading-relaxed text-(--text-secondary) line-clamp-2">{preview}</p>

      {/* Footer — likes, comments, CTA */}
      <div className="mt-auto flex items-center justify-between pt-3 border-t border-glass-border/(--opacity-soft)">
        <div className="relative z-deep flex items-center gap-4">
          {/* Like */}
          <button
            type="button"
            onClick={handleLike}
            className={cn(
              "flex items-center gap-1.5 transition-[color,transform] duration-fast active:scale-90",
              isLiked
                ? "text-error-text"
                : "text-(--text-secondary) hover:text-error-text/(--opacity-hover)"
            )}
            aria-label={isLiked ? t("common:aria.unlike") : t("common:aria.like")}
          >
            <span className={cn(celebrating && "news-heart-celebrate")}>
              <HeartIcon size={16} fill={isLiked ? "currentColor" : "none"} />
            </span>
            <span className="text-xs font-bold tabular-nums">{likesCount}</span>
          </button>

          {/* Comments */}
          <div className="flex items-center gap-1.5 text-(--text-secondary)">
            <CommentIcon size={16} />
            <span className="text-xs font-bold tabular-nums">{commentsCount}</span>
          </div>

          {/* Reading time (W59-10) */}
          {readingTime != null && (
            <div className="flex items-center gap-1 text-(--text-secondary)">
              <ClockIcon size={14} />
              <span className="text-[11px] font-medium tabular-nums">
                {readingTime} {t("common:time.minuteShort", { defaultValue: "min" })}
              </span>
            </div>
          )}

          {/* Bookmark */}
          {onToggleBookmark && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onToggleBookmark()
              }}
              className={cn(
                "flex items-center transition-[color,transform] duration-fast active:scale-90",
                isBookmarked
                  ? "text-brand"
                  : "text-(--text-secondary) hover:text-brand/(--opacity-hover)"
              )}
              aria-label={
                isBookmarked ? t("common:aria.removeBookmark") : t("common:aria.addBookmark")
              }
            >
              {isBookmarked ? (
                <BookmarkCheckIcon size={16} fill="currentColor" />
              ) : (
                <BookmarkIcon size={16} />
              )}
            </button>
          )}
        </div>

        {/* CTA — reveals on hover */}
        <div className="flex items-center gap-1 text-brand opacity-0 translate-x-1 transition duration-base ease-out group-hover:opacity-100 group-hover:translate-x-0 group-focus-within:opacity-100 group-focus-within:translate-x-0">
          <span className="text-xs font-semibold tracking-wide hidden sm:inline">
            {t("common:cta.learnMore")}
          </span>
          <ArrowIcon size={14} />
        </div>
      </div>
    </div>
  )
}

export default memo(NewsCardContent)
