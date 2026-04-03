import { cn } from "@/utils/cn"
import { motion } from "framer-motion"
import {
  ArrowUpRight as ArrowIcon,
  Bookmark as BookmarkIcon,
  BookmarkCheck as BookmarkCheckIcon,
  MessageCircle as CommentIcon,
  Heart as HeartIcon,
} from "lucide-react"
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
  onToggleLike,
  onToggleBookmark,
  hoveringDisabled,
}: NewsCardContentProps) => {
  const { t } = useTranslation(["common"])

  return (
    <div className="flex flex-1 flex-col gap-3 p-5">
      {/* Title */}
      <h3 className="font-semibold leading-snug text-text-primary text-base line-clamp-2"
      >
        <Link
          to="/news/$id"
          params={{ id: String(id) }}
          className={cn(
            "before:absolute before:inset-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/(--opacity-medium) focus-visible:ring-offset-2",
            hoveringDisabled && "pointer-events-none"
          )}
        >
          {title}
        </Link>
      </h3>

      {/* Preview */}
      <p className="text-sm leading-relaxed text-(--text-secondary) line-clamp-2">
        {preview}
      </p>

      {/* Footer — likes, comments, CTA */}
      <div className="mt-auto flex items-center justify-between pt-3 border-t border-glass-border/(--opacity-soft)">
        <div className="relative z-deep flex items-center gap-4">
          {/* Like */}
          <motion.button
            type="button"
            whileTap={{ scale: 0.85 }}
            onClick={(e) => {
              e.stopPropagation()
              onToggleLike()
            }}
            className={cn(
              "flex items-center gap-1.5 transition-colors duration-fast",
              isLiked
                ? "text-error-text"
                : "text-(--text-secondary) hover:text-error-text/(--opacity-hover)"
            )}
            aria-label={isLiked ? t("common:aria.unlike", { defaultValue: "Unlike" }) : t("common:aria.like", { defaultValue: "Like" })}
          >
            {isLiked ? (
              <motion.span
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 400, damping: 15 }}
                className="heart-pulse"
              >
                <HeartIcon size={16} fill="currentColor" />
              </motion.span>
            ) : (
              <HeartIcon size={16} />
            )}
            <span className="text-xs font-bold tabular-nums">{likesCount}</span>
          </motion.button>

          {/* Comments */}
          <div className="flex items-center gap-1.5 text-(--text-secondary)">
            <CommentIcon size={16} />
            <span className="text-xs font-bold tabular-nums">{commentsCount}</span>
          </div>

          {/* Bookmark */}
          {onToggleBookmark && (
            <motion.button
              type="button"
              whileTap={{ scale: 0.85 }}
              onClick={(e) => {
                e.stopPropagation()
                onToggleBookmark()
              }}
              className={cn(
                "flex items-center transition-colors duration-fast",
                isBookmarked
                  ? "text-brand"
                  : "text-(--text-secondary) hover:text-brand/(--opacity-hover)"
              )}
              aria-label={isBookmarked ? t("common:aria.removeBookmark", { defaultValue: "Remove bookmark" }) : t("common:aria.addBookmark", { defaultValue: "Bookmark" })}
            >
              {isBookmarked ? (
                <motion.span
                  initial={{ scale: 0.8 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 15 }}
                >
                  <BookmarkCheckIcon size={16} fill="currentColor" />
                </motion.span>
              ) : (
                <BookmarkIcon size={16} />
              )}
            </motion.button>
          )}
        </div>

        {/* CTA — reveals on hover */}
        <div className="flex items-center gap-1 text-brand opacity-0 translate-x-1 transition duration-base ease-out group-hover:opacity-100 group-hover:translate-x-0 group-focus-within:opacity-100 group-focus-within:translate-x-0">
          <span className="text-xs font-semibold tracking-wide hidden sm:inline">
            {t("common:cta.learnMore", { defaultValue: "Learn more" })}
          </span>
          <ArrowIcon size={14} />
        </div>
      </div>
    </div>
  )
}

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export default NewsCardContent
