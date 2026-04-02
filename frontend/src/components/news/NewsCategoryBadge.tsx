import { useTranslation } from "react-i18next"
import type { NewsCategory } from "@/features/news/categories"
import { getCategoryMeta } from "@/features/news/categories"

interface NewsCategoryBadgeProps {
  category: NewsCategory
  size?: "sm" | "md"
}

export function NewsCategoryBadge({ category, size = "sm" }: NewsCategoryBadgeProps) {
  const { t } = useTranslation(["news"])
  const { labelKey, color } = getCategoryMeta(category)

  return (
    <span
      className={
        size === "sm"
          ? "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
          : "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold uppercase tracking-wider"
      }
      style={{
        backgroundColor: `var(--cat-${color}-bg)`,
        color: `var(--cat-${color}-text)`,
      }}
    >
      {t(labelKey, { defaultValue: category })}
    </span>
  )
}
