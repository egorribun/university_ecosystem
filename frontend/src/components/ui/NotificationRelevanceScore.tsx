/**
 * NotificationRelevanceScore — Visual priority indicator
 *
 * Shows high/medium/low relevance dots next to notification items.
 * Foundation for future ML-based notification ranking.
 *
 * Wave 38: Smart notifications UI foundation
 */

import { cn } from "@/utils/cn"
import { useTranslation } from "react-i18next"

type Relevance = "high" | "medium" | "low"

interface NotificationRelevanceScoreProps {
  /** Relevance level */
  relevance: Relevance
  /** Optional className */
  className?: string
}

const relevanceConfig: Record<Relevance, { color: string; label: string }> = {
  high: { color: "bg-brand", label: "common:notifications.relevance.high" },
  medium: { color: "bg-warning-text", label: "common:notifications.relevance.medium" },
  low: { color: "bg-(--text-tertiary)", label: "common:notifications.relevance.low" },
}

export function NotificationRelevanceScore({
  relevance,
  className,
}: NotificationRelevanceScoreProps) {
  const { t } = useTranslation(["common"])
  const config = relevanceConfig[relevance]

  return (
    <div
      className={cn("flex items-center gap-1", className)}
      title={t(config.label)}
      aria-label={t(config.label)}
    >
      {(["high", "medium", "low"] as const).map((level, idx) => (
        <span
          key={level}
          className={cn(
            "block h-1.5 w-1.5 rounded-full transition-colors",
            idx <= ["high", "medium", "low"].indexOf(relevance)
              ? config.color
              : "bg-(--text-tertiary)/(--opacity-faint)"
          )}
          aria-hidden="true"
        />
      ))}
    </div>
  )
}
