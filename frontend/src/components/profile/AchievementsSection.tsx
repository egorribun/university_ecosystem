import { m } from "framer-motion"
import { useTranslation } from "react-i18next"
import { Shield } from "lucide-react"
import { SectionCard } from "@/components/settings"
import type { AchievementItem } from "./profileUtils"

type AchievementsSectionProps = {
  achievements: AchievementItem[]
  onAchievementClick: (ach: AchievementItem) => void
}

export const AchievementsSection = ({
  achievements,
  onAchievementClick,
}: AchievementsSectionProps) => {
  const { t } = useTranslation(["profile"])

  if (achievements.length === 0) return null

  return (
    <SectionCard className="p-6">
      <h2 className="text-lg font-bold tracking-tight text-text-primary mb-6">
        {t("profile:sections.achievements")}
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {achievements.map((ach) => (
          <m.div
            key={ach.key}
            whileHover={{ y: -2 }}
            className="flex items-start gap-3 p-4 rounded-2xl bg-(--bg-surface)/(--opacity-dim) border border-glass-border/(--opacity-subtle) hover:border-brand/(--opacity-soft) hover:bg-(--bg-surface)/(--opacity-medium) transition-all cursor-pointer group"
            onClick={() => onAchievementClick(ach)}
          >
            <div className="h-10 w-10 shrink-0 rounded-xl bg-brand/(--opacity-subtle) flex items-center justify-center text-brand group-hover:bg-brand group-hover:text-[var(--text-inverse)] transition-colors">
              <Shield className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-text-primary truncate group-hover:text-brand transition-colors">
                {ach.name}
              </h3>
              <p className="text-label-md text-(--text-secondary) opacity-strong mt-0.5 line-clamp-1">
                {ach.issuer || "Academic Board"}
              </p>
            </div>
          </m.div>
        ))}
      </div>
    </SectionCard>
  )
}

export default AchievementsSection
