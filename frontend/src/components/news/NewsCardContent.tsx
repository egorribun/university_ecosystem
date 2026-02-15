import { ContentCard } from "@/components/ui"
import { cn } from "@/utils/cn"
import { motion } from "framer-motion"
import {
  ArrowUpRight as ArrowOutwardIcon,
  MessageCircle as ChatBubbleOutlineIcon,
  Heart as FavoriteIcon,
} from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"

interface NewsCardContentProps {
  id: string
  title: string
  preview: string
  isLiked: boolean
  likesCount: number
  commentsCount: number
  onToggleLike: () => void
  hoveringDisabled: boolean
}

const NewsCardContent = ({
  id,
  title,
  preview,
  isLiked,
  likesCount,
  commentsCount,
  onToggleLike,
  hoveringDisabled,
}: NewsCardContentProps) => {
  const { t } = useTranslation(["common"])

  return (
    <ContentCard.Body className="flex flex-1 flex-col gap-2 p-fluid-card-p transition duration-base ease-out group-hover:-translate-y-px group-focus-visible/content:-translate-y-px md:gap-3">
      <ContentCard.Title className="text-fluid-h3 font-semibold line-clamp-none">
        <Link
          to={`/news/${id}`}
          className={cn(
            "before:absolute before:inset-0 focus:outline-none line-clamp-2",
            hoveringDisabled && "pointer-events-none"
          )}
        >
          {title}
        </Link>
      </ContentCard.Title>

      <p className="min-h-12 text-sm text-(--text-secondary) line-clamp-2 md:min-h-18 md:line-clamp-3">
        {preview}
      </p>

      <div className="relative z-deep flex items-center gap-4 mt-1 border-t border-glass-border pt-3">
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
        >
          <div className="relative">
            {isLiked ? (
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 400, damping: 15 }}
              >
                <FavoriteIcon size={18} fill="currentColor" />
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
        <span className="translate-y-1 text-sm font-semibold tracking-wide opacity-0 transition duration-base ease-out group-focus-within:translate-y-0 group-focus-within:opacity-100 group-hover:translate-y-0 group-hover:opacity-100">
          {t("common:cta.learnMore", { defaultValue: "Подробнее" })}
        </span>
        <ArrowOutwardIcon
          size={16}
          className="translate-x-0 text-(--primary-main) opacity-0 transition duration-base ease-out group-focus-within:translate-x-1 group-focus-within:opacity-100 group-hover:translate-x-1 group-hover:opacity-100"
        />
      </div>
    </ContentCard.Body>
  )
}

export default memo(NewsCardContent)
