/**
 * NewsQuickView — hover popover showing expanded preview of a news card.
 * Positioned above the card. Pointer-events-none so it doesn't block clicks.
 */

import { m, AnimatePresence } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { Calendar, MessageCircle, Heart } from "lucide-react"
import { getMoscowDate } from "@/utils/date"
import { useTranslation } from "react-i18next"
import { NewsCategoryBadge } from "./NewsCategoryBadge"
import type { NewsCategory } from "@/features/news/categories"

interface NewsQuickViewProps {
  visible: boolean
  title: string
  preview: string
  created_at: string
  likesCount: number
  commentsCount: number
  category?: NewsCategory
  /** Position relative to card. Default "top" (above card). */
  position?: "top" | "bottom"
}

export function NewsQuickView({
  visible,
  title,
  preview,
  created_at,
  likesCount,
  commentsCount,
  category,
  position = "top",
}: NewsQuickViewProps) {
  const { t } = useTranslation(["news"])
  const prefersReduced = useMediaQuery("(prefers-reduced-motion: reduce)")
  const dateLabel = created_at ? getMoscowDate(created_at) : ""

  return (
    <AnimatePresence>
      {visible && (
        <m.div
          role="tooltip"
          aria-hidden="true"
          initial={
            prefersReduced ? false : { opacity: 0, y: position === "top" ? 8 : -8, scale: 0.96 }
          }
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={
            prefersReduced
              ? { opacity: 0 }
              : { opacity: 0, y: position === "top" ? 4 : -4, scale: 0.98 }
          }
          transition={
            prefersReduced ? { duration: 0 } : { duration: 0.18, ease: [0.16, 1, 0.3, 1] }
          }
          className={`absolute left-0 right-0 z-floating pointer-events-none ${position === "top" ? "bottom-full mb-2" : "top-full mt-2"}`}
        >
          <div className="glass-layer-floating glass-noise rounded-xl p-4 shadow-premium-lift border border-glass-border/(--opacity-soft) max-w-[24rem] mx-auto">
            {/* Category + date */}
            <div className="flex items-center gap-2 mb-2">
              {category && <NewsCategoryBadge category={category} size="sm" />}
              {dateLabel && (
                <span className="flex items-center gap-1 text-[11px] text-(--text-secondary)">
                  <Calendar size={11} />
                  {dateLabel}
                </span>
              )}
            </div>

            {/* Title */}
            <h4 className="text-sm font-bold text-text-primary line-clamp-2 mb-1.5">{title}</h4>

            {/* Extended preview */}
            <p className="text-xs leading-relaxed text-(--text-secondary) line-clamp-4 mb-3">
              {preview}
            </p>

            {/* Stats footer */}
            <div className="flex items-center gap-3 text-[11px] text-(--text-secondary)">
              <span className="flex items-center gap-1">
                <Heart size={11} />
                {likesCount}
              </span>
              <span className="flex items-center gap-1">
                <MessageCircle size={11} />
                {commentsCount}
              </span>
              <span className="ml-auto text-brand font-semibold">
                {t("news:quickView.readMore")}
              </span>
            </div>
          </div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
