import { useTranslation } from "react-i18next"
import type { EventCategory } from "@/features/events/categories"
import { getCategoryMeta } from "@/features/events/categories"

interface EventCategoryBadgeProps {
  category: EventCategory
  size?: "sm" | "md"
}

/**
 * Color-coded category badge for event type.
 * Pattern source: components/news/NewsCategoryBadge.tsx
 */
export function EventCategoryBadge({ category, size = "sm" }: EventCategoryBadgeProps) {
  const { t } = useTranslation(["events"])
  const { labelKey, color } = getCategoryMeta(category)

  return (
    <span
      className={
        size === "sm"
          ? "events-badge-matte inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider"
          : "events-badge-matte inline-flex items-center rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider"
      }
      style={{
        "--_badge-accent": `var(--cat-${color}-text)`,
      } as React.CSSProperties}
    >
      <span
        className="mr-1 inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: `var(--cat-${color}-text)` }}
        aria-hidden="true"
      />
      {t(labelKey)}
    </span>
  )
}
